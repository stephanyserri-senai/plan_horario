# Regras de negócio do planejamento (memória do algoritmo)

Gerado por `scripts/gerar_regras_md.py` a partir de `backend/app/services/regras_institucionais.py`. Não edite à mão: altere o catálogo e gere de novo.

## Turmas e dias

- **Dias da turma** (`TURMA_DIAS`, obrigatória): Toda turma tem 5 dias presenciais (segunda a sexta) ou 4 dias presenciais + 1 dia de EAD (turma 80-20). _Onde: cadastro de turmas, importação, conformidade._
- **Turma de sábado** (`TURMA_SABADO`, obrigatória): Turma do turno de sábado tem aula presencial só no sábado, das 09:00 às 13:00 (4 aulas). Sábado não é usado por turmas da semana. _Onde: cadastro de turmas, gerador, validação._
- **Exceção: aperfeiçoamento e empresas** (`TURMA_FLEXIVEL`, obrigatória): Só atendimentos específicos de aperfeiçoamento e turmas para empresas podem ter menos dias por semana (o treinamento costuma ser curto). _Onde: cadastro de turmas, importação._
- **Turma PFP (manhã e tarde)** (`TURMA_PFP`, obrigatória): Turma PFP tem aula de manhã e de tarde: 08:00–12:00 e 13:00–17:00 (almoço 12:00–13:00). Cada metade é um turno inteiro: a manhã e a tarde podem ter UCs e instrutores diferentes. Na grade, as aulas aparecem nas linhas da manhã e da tarde (o limiar de horário aceita o início às 08:00 e às 13:00). Quem é da manhã dá o bloco 08–12; quem é da tarde, o 13–17. _Onde: cadastro de turmas, importação, gerador, validação, grade._
- **Dia EAD (turma 80-20)** (`TURMA_EAD`, obrigatória): O dia EAD (normalmente a sexta) não tem aula presencial: sai dos dias de aula, aparece na grade com a etiqueta EAD e a validação bloqueia aula nele. _Onde: cadastro, gerador, validação, grade, exportações._

## Matriz curricular

- **Lista de UCs fixa na versão cadastrada** (`VERSAO_CADASTRADA`, obrigatória): Cada versão da matriz tem a sua própria lista de UCs (nome, carga horária e se é presencial ou EAD). Enquanto a versão está em rascunho, as UCs podem ser incluídas, alteradas ou retiradas; depois de cadastrada (vigente ou encerrada), a lista fica fixa e não volta a rascunho. Para mudar, cria-se uma nova versão, que copia as UCs. Salas, certificação, dias por semana e ordem continuam ajustáveis. _Onde: cadastro de UCs, versões da matriz._
- **UC presencial ou EAD** (`UC_EAD`, obrigatória): Toda UC é presencial ou EAD. A opção EAD só existe nos cursos marcados como “prevê UCs EAD” (no cadastro do curso). A UC EAD é cursada a distância: não entra na geração da grade nem na demanda de instrutores e salas, e aparece no acompanhamento como “EAD (fora da grade)”. _Onde: cadastro de UCs, gerador, riscos, acompanhamento._

## Aulas e turnos

- **Turnos oficiais** (`TURNOS`, obrigatória): Turnos: Manhã 07:30–11:30; Tarde 13:30–17:30; Noite 18:30–22:00; Sábado 09:00–13:00. _Onde: estrutura fixa._
- **Turno inteiro** (`TURNO_INTEIRO`, obrigatória): Cada UC ocupa o turno inteiro do dia (4 aulas). Aula parcial só no fechamento da carga horária. _Onde: gerador, validação._
- **Carga horária em minutos reais** (`CONTAGEM_MINUTOS`, obrigatória): Cada aula vale o tempo que dura: 55 min de dia, 50 min à noite (60 min nas turmas PFP). O que falta para a carga da UC vira outra aula: uma UC de 20 h no matutino tem 22 aulas (1200 min ÷ 55); no noturno, 24 aulas (1200 ÷ 50). _Onde: carga horária, relatórios._
- **Divisão 3 + 2** (`DIVISAO_3_2`, preferência): Na semana, a turma pode ter duas UCs: uma com 3 dias e outra com 2, conforme a carga a cumprir, as horas da UC e o instrutor disponível. É uma opção, não obrigação. _Onde: análise do quadro (encaixe de turma nova)._

## Instrutores

- **Teto de 90% da jornada com aula** (`TETO_90`, obrigatória): Aula em no máximo 90% dos turnos da jornada: 40 h → 9 de 10 turnos (36 h); 20 h → 4 de 5 (16 h). O turno restante é planejamento (PL), projeto (PJ) ou reserva. _Onde: cadastro, importação, gerador, validação._
- **Ocupação ideal de 80%** (`OCUPACAO_IDEAL`, preferência): O ideal é até 80% da jornada com aula; entre 80% e 90% é atenção. _Onde: acompanhamento, quadro de instrutores._
- **Turnos de trabalho** (`JORNADA`, obrigatória): 40 h semanais = dois turnos por dia (MV ou VN); 20 h = um turno (M, V ou N). Sábado (09:00–13:00) é marcado à parte, por dia. _Onde: cadastro, portal, gerador._
- **Mensalista e horista** (`MODALIDADE`, obrigatória): Mensalista tem as horas garantidas (aula, PL, PJ ou TR); horista não (turno sem aula pode ser dispensa). A modalidade não depende do turno. _Onde: cadastro, agenda do instrutor._
- **Termo de horas do horista (ajustável)** (`TERMO_HORAS`, aviso): Mensalista tem jornada semanal fixa (ex.: 40 h), com aulas até 90% dela. Horista recebe todo mês um termo de horas: as horas de aula do mês (e outras ocupações) e, se for o caso, os dias da semana. O termo é adaptável: numa urgência (alguém num dia ou num total de horas fora do termo) ele é ajustado, desde que o instrutor concorde — o ajuste fica registrado com o motivo. Por isso aula fora do termo é alerta; o que impede, para horista e mensalista, é já estar ocupado e a carga máxima do contrato. A geração do semestre procura manter o horista dentro do termo; a simulação e a previsão de turmas não olham o termo. _Onde: disponibilidade e termos, validação, gerador, simulador, riscos, substituição._
- **Mensalistas ocupados primeiro** (`MENSALISTA_PRIMEIRO`, preferência): Todos os instrutores devem ser ocupados, mas na distribuição das aulas o mensalista (jornada garantida) tem prioridade: recebe primeiro, e o horista fica com o que os mensalistas habilitados não conseguem cobrir (ocupados, no teto de 90% ou sem a UC). O gerador de horários conta cada hora dada por horista como custo (critério prioridade_mensalista) e equilibra a carga dentro de cada grupo — entre os mensalistas e, no que sobra, entre os horistas, para não concentrar em poucos. As listas de instrutores possíveis, as sugestões de substituto e as correções de riscos mostram o mensalista antes do horista. _Onde: gerador, alocação manual, substituição, solicitações, riscos, simulador._
- **Nível básico ou técnico** (`NIVEL`, obrigatória): Instrutor BÁSICO só dá aula em aprendizagem industrial básica e qualificações (AIB, QUA); TÉCNICO, em todas as modalidades (inclusive AIT, ESP, HTC). Sem exceção. _Onde: gerador, validação, substituição, quadro._
- **UC transversal** (`UC_TRANSVERSAL`, obrigatória): UC transversal: qualquer instrutor da unidade pode dar (sem precisar marcar no perfil; vale só a certificação exigida, se houver). _Onde: cadastro de UCs, gerador, validação._
- **UC técnica: sim ou em partes** (`UC_TECNICA`, obrigatória): UC técnica: só quem marcou a UC no próprio perfil — 'Sim' (dá a UC) ou 'Em partes' (dá com alerta). _Onde: portal, cadastro, gerador, validação._
- **Área do instrutor** (`AREA`, obrigatória): O instrutor dá aula nas turmas da área principal e das outras áreas em que atua; fora disso só com exceção justificada. _Onde: gerador, validação._
- **Certificação exigida** (`CERTIFICACAO`, obrigatória): UC que exige certificação (ex.: NR-10) só com instrutor certificado e dentro da validade. _Onde: gerador, validação._
- **PL, PJ e TR na agenda** (`PL_PJ_TR`, obrigatória): Turno sem aula do instrutor pode ser PL (planejamento), PJ (projeto/outra atividade) ou TR (treinamento: liberado das aulas). O gerador não coloca aula nesses turnos; em PL/PJ o instrutor está na escola e pode substituir, em TR não. _Onde: agenda do instrutor, gerador, validação, substituição._

## Substituições e solicitações

- **Quem pode substituir** (`SUBST_PRESENCA`, obrigatória): Instrutor em PL ou PJ pode assumir no mesmo dia (já está na escola); com turno vazio, só se a substituição for planejada com pelo menos 1 dia de antecedência. _Onde: substituição._
- **Um instrutor por UC** (`UM_INSTRUTOR_POR_UC`, obrigatória): Cada UC de uma turma (por grupo, quando a UC divide a turma) tem um só instrutor do começo ao fim. Outro instrutor só entra por substituição (o titular continua sendo o da UC) ou por exceção justificada; passar a UC de vez a outro instrutor (remanejamento) troca o instrutor de todas as aulas futuras. O gerador completa a UC com quem já dá as aulas dela. _Onde: validação, gerador, substituição, riscos._
- **Horista fora do termo como substituto** (`SUBST_HORISTA_TERMO`, obrigatória): Mesmo sem horas ou sem o dia no termo do mês (ou fora da disponibilidade cadastrada), o horista aparece como opção de substituto. Só assume com a aprovação da supervisão e a concordância (e disponibilidade) dele; o termo do mês é ajustado junto e tudo fica registrado com o motivo. _Onde: substituição, termos de horas._
- **Painel de substituições** (`SUBST_PAINEL`, aviso): Menu Substituições: busca-se o instrutor, vê-se o que ele estaria fazendo no período (aula a aula) e marcam-se as aulas; o sistema indica quem pode assumir pela disponibilidade no dia e no horário — livres da área, de outra área/sem a UC (exceção), horistas fora do termo (com aprovação), livres em parte — com o mensalista antes do horista. _Onde: substituição._
- **Solicitações do instrutor** (`SOLICITACOES`, obrigatória): Pelo portal o instrutor pede folga ou substituição, com justificativa; o coordenador aprova ou recusa. Folga aprovada vira bloqueio na agenda e as aulas afetadas recebem sugestão de substituto. _Onde: portal, coordenação._

## Turmas

- **EPIs do curso em cada turma** (`EPI_TURMA`, aviso): O curso lista os EPIs exigidos por aluno. Cada turma recebe a lista com quantidade = alunos × por aluno e prazo = início da turma − antecedência; o controle marca comprado/separado e entregue. Prazo vencido sem entrega, ou a menos de 7 dias, vira aviso no Início e em Riscos. _Onde: cadastro de cursos, cadastro de turmas, controle de EPIs, riscos._
- **Turma modular: código sobe a cada semestre** (`TURMA_MODULAR`, obrigatória): No cadastro da turma diz-se se ela é modular (quantos módulos) e o módulo em curso. Modular: o código leva o módulo (HTC-AIT-2-34 = turma 34 no 2º módulo); não modular: código no padrão de sempre (HTC-AIT-34). Um módulo por semestre: ao criar o semestre seguinte, a turma passa ao próximo módulo (código, módulo e fim), até o último — 3 módulos a partir de 2026/2 vão até 2027/2. _Onde: cadastro de turmas, novo semestre._
- **UC que não termina no prazo** (`UC_FORA_DO_PRAZO`, obrigatória): Turma modular: o módulo precisa fechar no semestre, então a sugestão é reposição aos sábados (turno de sábado, com o instrutor da UC ou um habilitado), por exceção registrada e pela validação central. Turma não modular: as aulas que faltam passam para o próximo semestre (o prazo da UC vai para o fim dele). _Onde: riscos, sugestões, validação._

## Substituições e solicitações

- **Remanejar o único habilitado** (`REMANEJAMENTO`, preferência): UC que depende de um só instrutor: além de habilitar outro, o sistema sugere liberar o habilitado de outra UC dele, passando-a a quem está livre e pode assumi-la naquela turma (área, nível e certificação). _Onde: riscos, sugestões, substituição._

## Instrutores

- **Índice de aderência e PDI** (`ADERENCIA_INSTRUTOR`, aviso): Aderência a um curso = parte da carga horária das UCs técnicas que o instrutor pode ministrar ('sim' vale a UC inteira, 'em partes' metade; sem a certificação exigida a UC ainda não conta; UCs transversais ficam de fora; instrutor básico entra só nos cursos básicos). A aderência à área soma os cursos da área e a geral soma todas as áreas do instrutor. O que falta vira proposta de PDI (aprender, completar ou certificar), com prioridade pela demanda das turmas, por quantos outros instrutores já dão a UC e pelo ganho no curso; concluir um item pode marcar a UC como 'sim' no perfil. O instrutor acompanha o índice (por área e geral), a ocupação e o PDI no portal e registra as formações que concluir: as UCs indicadas são habilitadas na hora e a coordenação recebe uma observação para conferir. A equipe tem também o índice por área (média dos instrutores que atuam nela). _Onde: perfil do instrutor, portal do instrutor, PDI._

## Quadro e decisões

- **5 instrutores para 4 turmas** (`PROPORCAO_5_4`, aviso): Referência de 1.25 instrutor por turma. É um aviso, que pesa quando a folga dos instrutores não comporta uma turma nova. _Onde: quadro de instrutores._
- **Capacidade da área** (`CAPACIDADE_AREA`, obrigatória): Na capacidade de uma área contam os instrutores da área principal; um de outra área só entra se já dá aula em turma desta, com a fração da jornada que dedica a ela. _Onde: quadro de instrutores._
- **Sugestões e aprendizado** (`SUGESTOES`, preferência): Toda sugestão do sistema (substituto, sala, horário, habilitação, adiamento) pode ser aceita com um clique e é aplicada automaticamente, pela mesma validação. Aceites e recusas ficam registrados como decisões para revisar e calibrar o sistema. _Onde: grade, substituição, geração, diagnósticos._

## Salas

- **Laboratório especializado** (`SALA_AREA`, obrigatória): Laboratório especializado só recebe turmas da(s) área(s) dele; sala comum atende todas. _Onde: gerador, validação._
- **Capacidade e acessibilidade** (`SALA_CAPACIDADE`, obrigatória): A sala precisa comportar a turma (ou o grupo) e ser acessível quando a turma exige. _Onde: gerador, validação._
