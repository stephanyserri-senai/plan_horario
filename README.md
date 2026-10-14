# Plataforma de Planejamento Acadêmico, Horários e Capacidade Institucional

Aplicação web para planejar, gerar, validar, otimizar e publicar horários de aulas.
Ela centraliza turmas, UCs, instrutores, ambientes, equipamentos e calendários em um banco PostgreSQL único e substitui as planilhas separadas por turno.

O sistema **impede** conflitos de instrutor, turma (inclusive com divisão em grupos), ambiente e equipamentos, inclusive sob concorrência.
Ele também **gera** grades com Google OR-Tools CP-SAT, **mede** a ocupação real, **identifica gargalos**, **simula** novas ofertas sem tocar no planejamento vigente e **explica** cada recomendação com base nos dados cadastrados.

| Documento | Conteúdo |
|---|---|
| [README.md](README.md) | visão geral, instalação e execução local |
| [DEPLOY.md](DEPLOY.md) | publicação na Vercel, worker do otimizador e fluxo GitHub → Preview → Produção |
| [SUPABASE.md](SUPABASE.md) | banco, conexões, migrações, autenticação, RLS e backup |
| [SECURITY.md](SECURITY.md) | segredos, autenticação, autorização e riscos |
| [TESTING.md](TESTING.md) | testes automatizados e validações antes da publicação |
| [.env.example](.env.example) | todas as variáveis de ambiente |

---

## 1. Diagnóstico inicial e decisões

| Item | Situação encontrada | Decisão |
|---|---|---|
| Repositório | Vazio (sem commits) | Projeto inicializado do zero |
| Ambiente | Python 3.13, Node 22, PostgreSQL 16 com `btree_gist` e `intarray` | Backend em Python (mesma linguagem do solver), frontend em React + TypeScript |
| Solver | OR-Tools disponível via pip | CP-SAT em módulo próprio com contrato de dados puro (`app/solver/contrato.py`) |

### Arquitetura

```
frontend/ (React 18 + TypeScript + Vite + Recharts)
   │  HTTP/JSON (JWT)
backend/  (FastAPI + SQLAlchemy 2 + Alembic)
   ├─ app/api/            rotas (cadastros genéricos por metadados, planejamento, análise, segurança)
   ├─ app/services/       regras de negócio
   │    ├─ validacao.py   SERVIÇO CENTRAL DE VALIDAÇÃO (todas as regras obrigatórias)
   │    ├─ alocacao.py    gravação transacional (advisory locks + versão otimista)
   │    ├─ otimizacao.py  montagem do problema → solver → expansão em aulas datadas → validação
   │    ├─ cenarios.py    ciclo de aprovação/publicação, versões, comparação, restauração
   │    ├─ indicadores.py ocupação de ambientes/instrutores/turmas (dados reais)
   │    ├─ gargalos.py    fluxo máximo demanda→recursos compatíveis
   │    ├─ recomendacoes.py respostas explicáveis
   │    ├─ simulador.py   simulação agregada e completa de novas ofertas
   │    ├─ importacao.py / exportacao.py  XLSX/CSV/PDF
   │    └─ objetivo.py    função objetivo usada para comparar cenários
   └─ app/solver/         contrato + modelo CP-SAT (sem acesso ao banco)
PostgreSQL 16 (exclusion constraints GiST, transações, advisory locks)
```

O frontend nunca executa otimizações. O solver roda em uma fila assíncrona (`ThreadPoolExecutor`) e recebe/devolve somente dados serializáveis.
Por isso ele pode ser movido para um processo ou serviço separado sem mudar o contrato.

**Arquitetura híbrida de IA (seção 9.1):** motor de regras (`validacao.py`) → solver matemático (`solver/cpsat.py`) → função objetivo (`objetivo.py`) → análise de gargalos (`gargalos.py`) → recomendações explicáveis (`recomendacoes.py`) → infraestrutura de aprendizado (`registros_decisao`).
Nenhuma rede neural substitui o solver, e nenhuma recomendação pode violar restrição obrigatória: toda alternativa sugerida passa pela validação central.

---

## 2. Instalação e execução local

Pré-requisitos: Python ≥ 3.11, Node ≥ 20, PostgreSQL ≥ 14 com as extensões `btree_gist` e `intarray` (parte do `postgresql-contrib`).

```bash
# 1. Banco (ou use um PostgreSQL existente)
docker compose up -d db

# 2. Backend
cp .env.example .env               # na RAIZ do repositório; ajuste PLAN_DATABASE_URL etc.
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt    # completo (inclui OR-Tools e pytest)
alembic upgrade head               # migrações versionadas (cria extensões, restrições e RLS)
python -m app.seed                 # perfis, pesos padrão, configurações e 1º administrador (PLAN_ADMIN_*)
python -m app.seed --usuario-teste # opcional: usuário de TESTE admin / admin@123 (recusado em produção)
uvicorn app.main:app --reload --port 8000

# 3. Frontend (desenvolvimento, com proxy para a API)
cd ../frontend
npm ci
npm run dev                        # http://localhost:5173
```

Localmente, `PLAN_EXECUTOR=auto` executa o otimizador em *threads* do próprio servidor. Para reproduzir a arquitetura de produção (fila e worker), use `PLAN_EXECUTOR=fila` e rode `python -m app.worker` em outro terminal.

Fora da Vercel, `npm run build` gera `frontend/dist`, que a API serve na mesma origem. Para publicar na **Vercel + Supabase**, siga o [DEPLOY.md](DEPLOY.md).

### Usuário de teste

`python -m app.seed --usuario-teste` cria o administrador de **teste**, com login `admin` e senha `admin@123`. Ele serve para validar a instalação antes de cadastrar usuários reais.

* O comando é recusado com `PLAN_AMBIENTE=producao`.
* Enquanto o usuário existir, a API registra um alerta e `/api/saude` informa `usuario_teste_ativo: true`.
* Remova com `python -m app.seed --remover-usuario-teste`.
* No modo Supabase Auth, ver [DEPLOY.md](DEPLOY.md#7-usuário-de-teste-somente-desenvolvimentohomologação).

### Dados de demonstração (opcionais e removíveis)

```bash
python -m app.demo carregar   # cria uma unidade, cursos, turmas etc. com prefixo DEMO-
python -m app.demo remover    # remove tudo o que tem o prefixo DEMO-
```

Nenhum dado fictício é criado automaticamente. Indicadores e resultados são sempre calculados a partir do que está gravado.

### Backup e recuperação

```bash
DATABASE_URL=postgresql://plan:plan@localhost/plan_horario scripts/backup.sh backups/
pg_restore --clean --if-exists -d "$DATABASE_URL" backups/plan_horario_AAAAMMDD_HHMMSS.dump
```

Execuções do otimizador interrompidas por queda do servidor são marcadas como `falha` na inicialização. Como a aplicação do resultado é transacional, nenhuma aula parcial fica gravada.

---

## 3. Testes

```bash
# banco de testes separado (truncado a cada teste)
createdb plan_horario_test
cd backend && PLAN_TEST_DATABASE_URL=postgresql+psycopg://plan:plan@localhost:5432/plan_horario_test python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

Resultado atual: **62 testes passando** contra PostgreSQL real (36 funcionais + 26 de publicação e operação na Vercel/Supabase; ver [TESTING.md](TESTING.md)). Os testes verificam o resultado e a integridade final no banco.
O CI (`.github/workflows/ci.yml`) executa a mesma suíte e o build do frontend.

| Caso exigido (seção 20) | Teste |
|---|---|
| 1 Duas turmas na mesma sala | `test_conflitos::test_01_duas_turmas_mesma_sala` |
| 2 Instrutor em duas aulas | `test_02_instrutor_em_duas_aulas` |
| 3 Turma com duas UCs simultâneas | `test_03_turma_com_duas_ucs_simultaneas` |
| 4 Reservas concorrentes | `test_04_reservas_concorrentes` (threads reais) e `test_04b_exclusion_constraint…` |
| 5 Ambiente incompatível | `test_05_ambiente_incompativel` |
| 6 Excesso de capacidade | `test_06_excesso_de_capacidade` |
| 7 Instrutor sem habilitação | `test_07_instrutor_sem_habilitacao` |
| 8 Fora da disponibilidade | `test_08_fora_da_disponibilidade` |
| 9 Horário bloqueado / feriado (+ exceção autorizada) | `test_09_horario_bloqueado_e_feriado` |
| 10 Sobreposição parcial | `test_10_sobreposicao_parcial` |
| 11 Carga horária excedida (+ exceção) | `test_11_carga_horaria_excedida` |
| 12 UC sem conclusão possível no calendário | `test_otimizacao::test_12_…` |
| 13 Cenário viável otimizado | `test_13_cenario_viavel_otimizado` |
| 14 Cenário comprovadamente inviável | `test_14_cenario_comprovadamente_inviavel` |
| 15 Limite de tempo sem solução comprovada | `test_15_limite_de_tempo_sem_solucao_comprovada` |
| 16 Importação duplicada | `test_importacao_api::test_16_…` |
| 17 Importação com referências inválidas | `test_17_…` |
| 18 Alteração sem autorização / fora do escopo | `test_18_alteracao_sem_autorizacao` |
| 19 Comparação entre versões (+ restauração) | `test_cenarios_indicadores::test_19_…` |
| 20 Indicadores atualizados após mudança | `test_20_…` |
| 21 Preservação de horários fixos | `test_otimizacao::test_21_…` |
| 22/23 Simulação sem alterar o vigente e comparação atual × futuro | `test_22_23_…` |
| 24 Integridade após falha de transação | `test_conflitos::test_24_…`, `test_24b_versao_desatualizada` |
| 25 Ocupação por turno | `test_25_ocupacao_por_turno` |
| 26 Carga horária dos instrutores | `test_26_carga_horaria_dos_instrutores` |
| 27 Equipamentos compartilhados | `test_27_equipamentos_compartilhados` |
| 28 Divisão em grupos | `test_28_divisao_em_grupos` |
| Publicação exige validação, edição só por proposta | `test_publicacao_exige_validacao_e_bloqueia_edicao` |

---

## 4. Como os princípios obrigatórios foram atendidos

### Prevenção de conflitos e concorrência (seção 7)
* **Banco de dados:** `alocacoes` tem três *exclusion constraints* GiST:
  * cenário + instrutor + intervalo;
  * cenário + ambiente + intervalo, incluindo o tempo de preparação;
  * cenário + turma + **grupos** (`int[]` com `&&`) + intervalo.

  Uma aula da turma inteira ocupa todos os grupos; a aula do grupo *k* ocupa só `{k}`. Sobreposições, inclusive parciais, são impossíveis mesmo com uma inserção direta no banco.
* **Serviço:** antes de validar, a transação adquire `pg_advisory_xact_lock` para cada recurso envolvido, em ordem determinística: instrutor, ambiente, turma, turma×UC e equipamento. As regras que o banco não expressa (carga horária, limites de jornada, uso simultâneo de equipamentos) são verificadas sem condição de corrida.
* **Edição:** `versao` (controle otimista) recusa alterações sobre dados desatualizados, com mensagem clara. Uma alteração inválida não substitui o horário válido anterior (rollback).
* **Regras verificadas** (`validacao.py`): as 14 restrições da seção 7.1, mais acessibilidade, unidade de atuação do instrutor, interjornada, deslocamento entre unidades, funcionamento da unidade, situação da turma/UC e certificações (ex.: NR-10).
* **Severidades:** bloqueio, alerta, preferência e recomendação. Cada ocorrência registra recurso, data, intervalo, turma, UC, instrutor, ambiente, origem e descrição.
* **Alternativas:** ao bloquear, a API calcula instrutores habilitados livres, ambientes compatíveis livres e horários livres na semana, todos já validados.

### Modelo temporal
* `atividades`: padrão semanal recorrente.
* `alocacoes`: aulas datadas, com `inicio`/`fim` reais. Os conflitos comparam instantes, não códigos de período.
* Recorrências pulam feriados e recessos do calendário. Exceções (`dia_letivo_extra`, `horario_especial`) e bloqueios temporários são respeitados.

### Geração e otimização (seção 8)
* CP-SAT decide o padrão semanal: dia, bloco de períodos, instrutor e ambiente.
* As restrições só valem entre atividades cujas janelas de datas se sobrepõem. Isso permite UCs sequenciais da mesma turma no mesmo semestre.
* **Escopos:** turma, curso, turno, unidade, instituição, somente pendentes e simulação. Aulas fixas são preservadas; flexíveis podem ser regeneradas.
* **Status distintos:** `OTIMA`, `VIAVEL`, `SEM_SOLUCAO_NO_LIMITE` (nunca reportado como inviável), `INVIAVEL` (só quando provado), `MODELO_INVALIDO` e `SEM_DEMANDA`.
* **Inviabilidade explicada:** quando provada, o sistema roda uma busca parcial diagnóstica, explica cada atividade não alocada (`recomendacoes.explicar_nao_alocacao`) e relaciona os gargalos agregados.
* **Expansão:** cada aula datada gerada passa pela validação central antes da gravação. Datas pontualmente inviáveis são puladas, a aula segue para a semana seguinte, e o risco de não conclusão é reportado.
* **Função objetivo:** 14 critérios configuráveis (`app/solver/criterios.py`), com unidade documentada e escala `pontos = peso × valor bruto`.
  * Cada execução grava uma cópia dos pesos e da versão do conjunto.
  * A comparação entre cenários recalcula todos com o **mesmo** conjunto de pesos e explica, critério a critério, por que um ficou à frente.
  * Restrições obrigatórias nunca viram penalidades.
* **Registro de cada execução:** identificador, cenário, parâmetros, status, tempo, resultado, motivo de término e diagnósticos.

### Indicadores (seção 10)
* Ocupação temporal = horas ocupadas ÷ horas efetivamente disponíveis × 100. As horas disponíveis consideram dias letivos, períodos de aula e disponibilidade do ambiente, descontados bloqueios e manutenção.
* A utilização da capacidade física é apresentada separadamente.
* A ocupação do instrutor usa a capacidade efetiva de ensino, `min(limite letivo, disponibilidade declarada)`, e não a jornada contratual.
* Todos os KPIs abrem o detalhamento de origem.

### Gargalos e simulador (seções 11 e 12)
* Fluxo máximo (OR-Tools) entre demanda e recursos **compatíveis** (tipo, capacidade, acessibilidade, equipamentos, turno, habilitação). Horas de recursos não intercambiáveis nunca são somadas.
* Seis tipos de déficit distintos, cada um com a fórmula do cálculo e alternativas.
* **Simulação agregada:** estimativa explícita, sem gravação.
* **Simulação completa:**
  * turmas isoladas (`turmas.simulacao_id`) e cópia do cenário base com tipo `simulacao`, que nunca pode ser publicado;
  * o solver confirma ou refuta a viabilidade;
  * alternativas (outro turno, incluir sábado) são simuladas;
  * o resultado inclui a comparação entre o cenário atual e o futuro.

### Versionamento, aprovação e auditoria (seção 14)
* **Estados:** em elaboração → em otimização → em validação → aguardando aprovação → aprovado → publicado → arquivado.
* A publicação revalida o cenário, exige zero bloqueios e arquiva o publicado anterior. Há no máximo um publicado por unidade, garantido por índice único parcial.
* Um horário publicado só muda por **proposta de alteração**: cópia, edição, validação, impacto (recursos afetados) e aprovação.
* Cada transição grava uma **versão** (snapshot + indicadores). Versões podem ser comparadas e restauradas.
* `historico_auditoria` registra cadastros, importações, alocações, tentativas bloqueadas, pesos, execuções, aprovações, publicações, exportações, acessos e alterações de permissões, na mesma transação da operação auditada.

### Segurança (seções 15 e 19)
* JWT, senhas com bcrypt, nenhuma credencial no repositório (`.env.example`).
* Perfis configuráveis (tabela `permissoes_perfil`) e escopo por unidade, curso ou turma (`permissoes`), sempre validados no servidor.
* O e-mail do instrutor só é exibido a perfis com `dados_pessoais.ler`. Exportações exigem permissão e são auditadas.
* Ambientes separados via `PLAN_AMBIENTE`. Migrações versionadas (Alembic). Paginação e índices em todas as consultas de listagem.

### Importação (seção 13)
* XLSX (várias planilhas) e CSV, com detecção do tipo e mapeamento revisável.
* Referências resolvidas por códigos e matrículas. Correspondência por nome gera aviso e é recusada se ambígua.
* Prévia com ação por linha (criar, atualizar, sem alteração, erro), duplicidades no arquivo e dados ausentes.
* Confirmação transacional e relatório XLSX.
* Hash SHA-256 detecta reimportação; chaves naturais impedem duplicação.
* Aulas importadas passam pela validação central e só entram em cenários em elaboração.

### Aprendizado de máquina (seção 9.3 / Fase 8)
* `registros_decisao` guarda sugestões, seleções, rejeições, alterações manuais com motivo, aprovações, reprovações e resultados de cenários.
* Um administrador revisa, corrige ou exclui cada registro e decide se ele entra no treinamento (`incluir_treinamento`). Nada é incluído automaticamente.
* `/api/aprendizado/avaliacao` informa a prontidão (mínimo de 500 registros revisados), a linha de base (função objetivo com pesos explícitos) e o protocolo de avaliação (treino/validação/teste, métrica, critério de adoção).
* **Nenhum modelo foi treinado**, porque ainda não há dados históricos. Isso segue a instrução de avaliar a necessidade antes de implementar uma rede neural.

---

## 5. Limitações conhecidas e próximas tarefas

* **Modelo semanal:** o solver decide um padrão semanal por atividade. Exceções pontuais (feriados, bloqueios de um dia, aulas avulsas) são tratadas na expansão, pulando a data e estendendo a aula para a semana seguinte, com alerta de risco quando o prazo não comporta.
* **Aproximações nos critérios de preferência do solver:** janelas e equilíbrio de carga são aproximados no padrão semanal. A régua oficial de comparação (`objetivo.py`) é calculada sobre as aulas datadas.
* **Aulas avulsas fixas** (uma única ocorrência) não restringem o padrão semanal no solver; são respeitadas na expansão.
* **Gargalos** são uma análise agregada: a ausência de déficit não garante uma grade; só o gerador comprova.
* **Otimizador fora da Vercel:** em produção serverless, o gerador e a simulação completa rodam num worker separado (`python -m app.worker`), com fila no próprio PostgreSQL (`SKIP LOCKED` e *heartbeat*). Sem o worker publicado, essas execuções ficam na fila. Ver [DEPLOY.md](DEPLOY.md).
* **Próximas tarefas sugeridas:**
  * testes de interface automatizados no CI (Playwright);
  * edição em lote na grade;
  * notificações de aprovação;
  * importador de layouts de planilha legados específicos (com mapeamento salvo);
  * treinamento offline do modelo de preferências quando houver dados revisados suficientes.
