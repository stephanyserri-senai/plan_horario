# Planejamento Acadêmico (SENAI-ES) — memória do projeto

Plataforma de planejamento de horários, capacidade e ocupação: FastAPI + PostgreSQL (backend/), React + TS (frontend/),
deploy em Vercel + Supabase (SQL aplicado à mão pelo SQL Editor; ver SUPABASE.md).

## Regras de negócio
As regras da instituição (dias da turma, sábado, EAD 80-20, turno inteiro, teto de 90%, nível básico/técnico,
UC transversal/técnica, substituição, solicitações, quadro 5:4...) estão em **docs/REGRAS_DE_NEGOCIO.md**, gerado de
`backend/app/services/regras_institucionais.py`. Ao mudar uma regra: altere o código que a aplica, o catálogo e rode
`python scripts/gerar_regras_md.py` (um teste confere que o documento está em dia).

## Convenções
- Nomenclatura: TURNO é sempre M, V ou N (matutino, vespertino, noturno) em telas, planilhas e termo; códigos internos M, V, N e,
  no sábado, "S" (M 09–13) e "SV" (V 14–18) — `regras_aula.letra_turno`/`eh_sabado` (o antigo código "T" virou "V" na 0025). Para contar aulas na semana use
  "dias de aula" (cada dia ocupa um turno inteiro), nunca "turnos por semana". Turmas PFP têm manhã (08–12) e tarde
  (13–17); cada metade é um turno, com UC e instrutor próprios (turno oculto "I"; na grade caem nas linhas da manhã e da tarde).
- Carga horária em minutos reais: cada aula vale 55 min (dia) ou 50 min (noite); o que falta vira outra aula
  (UC de 20 h no matutino = 22 aulas). "hora_aula" (60 min) é só opção nas configurações.
- Ausências do instrutor: PL (planejamento) e PJ (projeto) ficam na escola; TR (treinamento) libera das aulas
  (não é substituto possível e o gerador evita).
- Curso com UMA sigla; versões da matriz por público (`matrizes_curriculares.tipo_oferta`, texto livre até 30: PAGANTE, SEDU, AIT, HTC…;
  única por curso + versão + público); a turma escolhe a versão (`matriz_id` no formulário, filtrado pelo curso; vazio = `_matriz_padrao`);
  planilha de estrutura/turmas com a coluna "Público / versão do curso" (`oferta`). Sem pré-requisitos.
- EPIs: cadastrados no curso (`epis_curso`); cada turma recebe o controle (`epis_turma`: quantidade, prazo, comprado/separado,
  entregue) via `services/epis.sincronizar_turma`, chamado ao criar/alterar/duplicar/importar turma. Curso com
  `dispensa_epi` não precisa de EPI (lista vazia, não aparece como pendente).
- Interface e mensagens em português; nada de dados fictícios fora da demonstração (`backend/app/demo_semestre.py`).
- Perfis: o código interno `coordenador` aparece como **Supervisão** (rótulo e textos; não renomear o código). Logins da equipe
  NÃO ficam no repositório (dados pessoais): tela Usuários ou SQL entregue à parte; senha inicial nunca em texto no repositório. `usuarios.trocar_senha`: no primeiro
  acesso o usuário só usa `/api/auth/*` até definir a senha (`deps.get_contexto`; tela `PrimeiroAcesso` no App).
- UNIDADES E ÁREAS NUNCA SÃO APAGADAS pelos scripts de limpeza (só as de demonstração, código DEMO-...).
- Início do projeto com dados reais: `backend/sql/limpar_demo_iniciar_projeto.sql` (uma vez) apaga o demo/testes e grava
  `configuracoes.producao_iniciada`; com essa marca, os scripts de demo/teste (e a própria limpeza) recusam rodar. Novo script de
  demo/teste deve ter a mesma trava.
- Migrações Alembic não destrutivas; para cada migração, gere o SQL do Supabase com `scripts/gerar_sql_migracoes.sh`
  (`backend/sql/atualizacao_NNNN.sql`) e cite-o no SUPABASE.md. O demo (`backend/sql/demo_semestre_completo.sql`)
  é gerado por `scripts/gerar_semestre_demo_sql.py`.
- Nunca expor chaves `service_role`, senhas ou segredos no frontend ou no repositório.
- Toda alocação passa pela validação central (`backend/app/services/validacao.py`).
- Turma: o público (SEDU, PAGANTE, aprendizagem…) é obrigatório quando o curso tem versões para mais de um (regra TURMA_PUBLICO;
  `cadastros._publicos_do_curso`; tela `VersaoDoCurso`: escolhe o público e depois a versão). Sábado do instrutor independe da
  jornada da semana: `disp_sabado` (M, V, MV ou vazio; `cadastros._gravar_sabado`; coluna "Sábado (M, V ou MV)" na planilha).
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
- **Ninguém trabalha mais de 44 h por semana** (regra LIMITE_44H, `regras_aula.MAX_HORAS_SEMANA`): aula + PL/PJ/TR + urgência e
  outras somadas. Cadastro/importação (carga até 44 h), termo (`termos._limite_semanal`), validação (bloqueio LIMITE_44H) e gerador.
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
  UC: carga TOTAL = `carga_horaria_ead` + `carga_horaria_presencial`, `modalidade` presencial/ead/semipresencial (≠ modalidade do curso;
  nada propaga) e `divisao_confirmada` (falso = registro antigo a conferir). Regra única em `services/carga_uc.py` (`resolver`,
  `ch_presencial`, gancho no modelo). SÓ a presencial vira aula/sala/agenda (gerador, validação UC_SO_EAD, simulador, riscos); horas
  em minutos uma vez só, na geração. Tutoria/encontro remoto = bloqueio `tutoria_ead` (sigla EAD na agenda; conta no 44 h e na carga
  docente). Importação: colunas "Carga horária da UC (h)" (total), "Modalidade da UC", "Carga horária EaD (h)", "Carga horária
  presencial (h)" (a coluna "Modalidade" é do curso); planilha antiga pede a distribuição na prévia (`opcoes.distribuicao`); prévia com
  `cargas` por matriz; versão cadastrada aceita corrigir só a divisão. Impacto/correção: `services/correcao_carga.py`,
  `GET /api/cenarios/{id}/impacto-carga`, `POST .../aplicar-carga` (preserva realizadas e fixas). Indicadores: `indicadores.cargas_separadas`.
- Um instrutor por UC (turma × UC × grupo): `validacao.titular_da_uc` + regra UM_INSTRUTOR_POR_UC (bloqueio; alerta com exceção
  regra_academica; não vale na substituição). O gerador restringe a atividade ao titular. `passar_uc` usa `substituir(..., transferir=True)`.
- Substituições: página `/substituicoes` (busca do instrutor → agenda semanal em cartões via `GET /api/substituicoes/aulas-do-instrutor` →
  clicar na aula abre o pop-up: só a aula, o dia, a UC no período ou tudo →
  `GET /api/substituicoes/candidatos?alocacao_ids=`). Horista fora do termo/disponibilidade = grupo `aprovacao`; `POST /api/substituicoes`
  com `aprovado_supervisao` e `concordancia` relaxa a disponibilidade (exceção "aprovada pela supervisão") e ajusta o termo do mês.
- Pedidos de impressão (regra IMPRESSAO_PRAZO): `services/impressoes.py`, tabela `solicitacoes_impressao`; portal (aba Impressões,
  `/api/portal/impressoes`, PDF até 4 MB em `arquivo_pdf` via `POST .../{id}/pdf`, baixa em `GET .../{id}/pdf`) até a quinta da semana
  anterior ao uso (`prazo_para`); coordenação em `/impressoes` (`PUT /api/impressoes/{id}`:
  em_producao → pronta → entregue, ou recusada com motivo; notifica o instrutor). Aba de termo/jornada no perfil vale para todos
  (mensalista vê a jornada fixa).
- Agendamento de ambientes (regra AGENDAMENTO_AMBIENTE; substitui a planilha): `services/agendamentos.py`, tabela `agendamentos_ambiente`;
  grade ambientes × dias × turnos (`grade`: aula da grade PUBLICADA, bloqueio, reservado, pendente, feriado, livre) em
  `GET /api/ambientes/agenda` e `/api/portal/ambientes/agenda`; pedido do portal fica pendente e segura o horário; a supervisão
  confirma (cria `Bloqueio` tipo evento no ambiente → gerador/validação respeitam) ou recusa com motivo; página `/agendamentos`.
- Diárias (regra DIARIAS): `services/diarias.py`, tabela `solicitacoes_diarias`; a supervisão registra em `/diarias`
  (`/api/diarias`, situação em `POST /api/diarias/{id}/situacao`: solicitada → aprovada → paga, ou recusada/cancelada com motivo); aviso no portal.
- Instrutor: `gestor_imediato` e uniforme (`jaleco_np`, `jaleco_pmg`, `jaleco_num` (qualquer número), `tamanho_blusa`, `numero_botina`) no cadastro, no
  portal (tamanhos editáveis pelo instrutor), na planilha de levantamento (modelo, importação `CAMPOS_UNIFORME` e exportação).
- Riscos: `services/resolucoes.sugerir` dá uma correção por caso (acao para `services/sugestoes.aplicar`); trocar sala e
  remarcar valem também com o horário publicado (ajuste operacional, como a substituição).

## Testes locais
`service postgresql start`; `cd backend && python -m pytest -q`; frontend: `cd frontend && npx tsc --noEmit -p . && npm run build`.
