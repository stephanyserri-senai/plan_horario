# Publicação na Vercel (com Supabase e worker do otimizador)

Este guia publica o projeto **existente** a partir do GitHub. Nenhum repositório novo é necessário.

Leia também [SUPABASE.md](SUPABASE.md) (banco e autenticação), [SECURITY.md](SECURITY.md) e [TESTING.md](TESTING.md).

## 1. Arquitetura de produção

```
Navegador ──HTTPS──► Vercel
                      ├─ CDN: frontend React (frontend/dist)
                      └─ Função Python: /api/* (api/index.py → backend/app, FastAPI)
                              │  SQL (pooler em modo transação, porta 6543)
                              ▼
                      Supabase ── PostgreSQL (dados, fila de jobs, auditoria)
                              │   Auth (login, convites, recuperação de senha)
                              ▲
                      Worker do otimizador (container com OR-Tools)
                      python -m app.worker — Render / Railway / Fly.io / Cloud Run / VM
```

**Por que um worker separado?** O gerador de horários (Google OR-Tools CP-SAT) e a simulação completa:
* dependem do OR-Tools, que com pandas e numpy ocupa cerca de 220 MB. A função da Vercel tem limite de 250 MB, e só a API sem OR-Tools já ocupa cerca de 135 MB;
* podem rodar por minutos, mais que o tempo máximo de uma função;
* precisariam de *threads* em segundo plano, que não sobrevivem em serverless.

Por isso, na Vercel a API apenas **registra** a execução na fila (tabela `execucoes_otimizacao` ou `simulacoes_capacidade`, status `pendente`). O worker a reserva com `SELECT … FOR UPDATE SKIP LOCKED`, executa e grava o resultado na mesma transação, depois de passar pela validação central.

Todo o resto roda na Vercel: cadastros, grade, validações, indicadores, gargalos, simulação agregada, importação e exportação. **Sem o worker, as execuções ficam "na fila"** (a tela de Geração inteligente avisa). Nenhum resultado é simulado.

| Componente | Onde roda | Dependências | Comando |
|---|---|---|---|
| Frontend | Vercel (estático) | `frontend/package.json` | `npm run build` → `frontend/dist` |
| API | Vercel (Python serverless) | `requirements.txt` (raiz; igual a `backend/requirements-api.txt`, sem OR-Tools) | `api/index.py` |
| Worker | Container (ex.: Render) | `backend/requirements.txt` (com OR-Tools) | `python -m app.worker` (`backend/Dockerfile`) |
| Banco/Auth | Supabase | — | migrações Alembic |

Arquivos de configuração: `vercel.json`, `.vercelignore`, `.python-version`, `api/index.py`, `requirements.txt`, `backend/Dockerfile`.

## 2. Pré-requisitos

1. Conta na Vercel com acesso à organização ou usuário dono do repositório no GitHub.
2. Projeto Supabase criado e migrado (passos 1 a 5 de [SUPABASE.md](SUPABASE.md)). Recomenda-se um projeto para homologação e outro para produção.
3. Conta num serviço de containers para o worker (Render, Railway, Fly.io, Google Cloud Run com instância mínima 1, ou uma VM).
4. Testes locais passando ([TESTING.md](TESTING.md)).

## 3. Conectar o repositório à Vercel

1. Vercel → **Add New… → Project → Import Git Repository** → selecione o repositório **existente** deste projeto.
2. Em **Configure Project**:
   * **Root Directory:** `.` (raiz do repositório; não use `frontend`).
   * **Framework Preset:** *Other*. O `vercel.json` já define install, build e output:
     * install: `cd frontend && npm ci`
     * build: `cd frontend && npm run build`
     * output: `frontend/dist`
   * A função Python `api/index.py` é detectada automaticamente. As dependências vêm de `requirements.txt` na raiz, e a versão do Python de `.python-version` (3.12).
3. Cadastre as variáveis de ambiente (seção 4) **antes** do primeiro deploy.
4. Em **Settings → Git → Production Branch**, defina a branch que publica em produção (normalmente `main`).
   Todas as outras branches e *pull requests* geram **Preview Deployments** automaticamente.
5. Clique em **Deploy**.

> A branch atual de desenvolvimento é `claude/academic-scheduling-platform-nlhi9f`. Faça o *merge* em `main` (via *pull request*) quando quiser publicar em produção. Não é preciso alterar a branch principal do repositório.

## 4. Variáveis de ambiente

Cadastre em **Vercel → Project → Settings → Environment Variables**. Use **Preview** e **Production** com valores diferentes (bancos diferentes).
Todos os nomes, com exemplos, estão em [`.env.example`](.env.example).

| Variável | Vercel | Worker | Público? | Observação |
|---|:-:|:-:|:-:|---|
| `PLAN_AMBIENTE` | ✔ | ✔ | — | `producao` na Production; `homologacao` na Preview |
| `PLAN_DATABASE_URL` | ✔ | ✔ | segredo | Vercel: *Transaction pooler* (porta **6543**). Worker: *Session pooler* (5432) ou conexão direta |
| `PLAN_AUTH_MODO` | ✔ | ✔ | — | `supabase` (recomendado) ou `local` |
| `PLAN_SUPABASE_URL` | ✔ | ✔ | público | `https://<ref>.supabase.co` |
| `PLAN_SUPABASE_ANON_KEY` | ✔ | — | público | chave *anon/publishable*; entregue ao navegador por `/api/auth/config` |
| `PLAN_SUPABASE_JWT_SECRET` | ✔ | — | **segredo** | só se o projeto usar o segredo JWT legado (HS256) |
| `PLAN_SUPABASE_SERVICE_ROLE_KEY` | opcional | — | **segredo** | permite enviar convites pela tela de usuários |
| `PLAN_JWT_SECRET` | ✔ se `local` | — | **segredo** | 32+ caracteres aleatórios |
| `PLAN_URL_PUBLICA` | ✔ | — | público | URL do site (links de convite e recuperação) |
| `PLAN_EXECUTOR` | `fila` | `fila` | — | na Vercel o padrão (`auto`) já resulta em `fila` |
| `PLAN_GITHUB_TOKEN` | recomendado | — | **segredo** | inicia o worker do GitHub Actions na hora (ver seção 5, Opção A) |
| `PLAN_GITHUB_REPO`, `PLAN_GITHUB_REF` | opcional | — | — | `dono/repositorio` e branch; vazio = detectados automaticamente na Vercel |
| `PLAN_CORS_ORIGENS` | opcional | — | — | só se outro domínio consumir a API |
| `PLAN_LOG_LEVEL` | opcional | opcional | — | `INFO` |
| `PLAN_SOLVER_THREADS`, `PLAN_SOLVER_LIMITE_MAX_S` | — | ✔ | — | ajuste à CPU do worker |

* **Integração Supabase da Vercel (Marketplace):** se você a usar, ela cria `POSTGRES_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` e `SUPABASE_SERVICE_ROLE_KEY`. A API aceita esses nomes como alternativa aos `PLAN_*`.
  * `POSTGRES_URL` é o pooler de transação.
  * Confira se essas variáveis não ficam expostas como `NEXT_PUBLIC_*` com segredos: este projeto não usa `NEXT_PUBLIC_*` para nada além de URL e chave pública.
* Nenhuma variável `VITE_*` é necessária: o frontend lê a configuração pública em tempo de execução (`/api/auth/config`).
* A API **recusa iniciar** com configuração insegura em produção (por exemplo, `PLAN_JWT_SECRET` fraco no modo local, banco em `localhost` ou Supabase incompleto). O motivo aparece nos logs da função.

## 5. Publicar o worker do otimizador

### Opção A — GitHub Actions (gratuita; em uso na homologação)

O workflow `.github/workflows/worker.yml` processa a fila:
* automaticamente, a cada cerca de 15 minutos (o GitHub pode atrasar execuções agendadas);
* manualmente, em **Actions → Worker do otimizador → Run workflow**.

Para economizar minutos, ele primeiro consulta a fila e só instala o OR-Tools e executa `python -m app.worker --uma-vez` quando há jobs pendentes.

1. **GitHub → Settings → Secrets and variables → Actions → New repository secret:**
   * `PLAN_DATABASE_URL`: a URL do **Session pooler** (porta 5432):
     `postgresql://postgres.<ref>:<senha>@aws-1-<regiao>.pooler.supabase.com:5432/postgres`
2. Opcional, na aba **Variables**: `PLAN_AMBIENTE` (padrão `homologacao`) e `PLAN_AUTH_MODO` (padrão `local`).
3. Para testar, rode **Run workflow** e confira o log do passo "Há jobs na fila?".
4. **Início imediato (recomendado — o planejador nunca precisa abrir o GitHub):**
   1. GitHub → foto do perfil → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
   2. *Repository access*: **Only select repositories** → este repositório.
   3. *Permissions → Repository permissions → Actions*: **Read and write** (nada além disso).
   4. Defina uma validade (ex.: 1 ano) e gere o token.
   5. Vercel → Settings → Environment Variables: `PLAN_GITHUB_TOKEN` = o token (marque *Sensitive*) → **Redeploy**.

   Com isso, ao clicar em **Gerar horários** ou **Montar grade de teste**, a API dispara o workflow na hora e o resultado aparece em cerca de 2–5 minutos. Se o disparo falhar, nada se perde: o job continua na fila e o agendamento a cada ~15 min o processa. A tela mostra "Processar agora" se a espera passar do normal. O token fica só no servidor (nunca vai ao navegador) e só consegue disparar workflows deste repositório.

**Limitações:**
* sem `PLAN_GITHUB_TOKEN`, a geração não é imediata (espera de até cerca de 15–20 minutos);
* repositórios privados têm cota mensal de minutos gratuitos;
* execuções agendadas só ocorrem na branch padrão e são suspensas após 60 dias sem atividade no repositório.

Para resposta em segundos, use a opção B.

### Opção B — Serviço de container sempre ligado

Exemplo com **Render** (outros provedores são análogos):

1. Render → **New → Background Worker** → conecte o **mesmo** repositório do GitHub.
2. **Root Directory:** `backend` · **Runtime:** Docker (usa `backend/Dockerfile`; o comando padrão é `python -m app.worker`).
3. Variáveis:
   * `PLAN_AMBIENTE` e `PLAN_AUTH_MODO`, iguais às da Vercel;
   * `PLAN_DATABASE_URL`, com o pooler de **sessão** (porta 5432) ou a conexão direta;
   * `PLAN_EXECUTOR=fila`.
4. Plano: CPU e memória compatíveis com o porte da instituição. 1 vCPU e 1–2 GB atendem dezenas de turmas; ajuste `PLAN_SOLVER_THREADS` ao número de vCPUs.
5. **Auto-deploy:** ative para que o worker acompanhe a mesma branch da produção. Use um worker separado, apontando para o banco de homologação, se quiser testar *previews* com otimização.
6. Escala: vários workers podem rodar ao mesmo tempo, porque o `SKIP LOCKED` garante que nenhum job é processado duas vezes.

Alternativas sem Docker: `pip install -r backend/requirements.txt && cd backend && python -m app.worker`.
Para execução agendada em vez de contínua: `python -m app.worker --uma-vez` via cron.

**Diagnóstico:** `GET /api/saude` mostra:
* `fila.execucoes_pendentes` e `fila.simulacoes_pendentes`;
* `worker`: último sinal de vida, estado e job atual;
* `migracao`: revisão do banco.

Jobs cujo worker parou de responder por mais de `PLAN_WORKER_HEARTBEAT_EXPIRA_S` (padrão 300 s) são marcados como falha. Como a gravação é transacional, nenhuma aula parcial fica no banco.

## 6. Primeiro deploy — passo a passo

1. Supabase: criar projetos, aplicar migrações, configurar Auth e criar o primeiro administrador ([SUPABASE.md](SUPABASE.md)).
2. Vercel: importar o repositório, cadastrar variáveis (Preview e Production) e fazer o deploy.
3. Worker: publicar e conferir em `https://<seu-site>/api/saude` que `worker.estado` é `ocioso` e `migracao` é `0002`.
4. Acessar o site e entrar com o administrador.
   * Em homologação, é possível usar o usuário de teste (seção 7).
   * Em produção, use um administrador real.
5. Validar em **Preview** antes de promover ([TESTING.md](TESTING.md#validação-em-preview)).
6. Promover para produção: faça o *merge* na *Production Branch* (ou use **Promote to Production** na Vercel).

## 7. Usuário de teste (somente desenvolvimento/homologação)

Para validar a instalação antes de cadastrar usuários reais:

```bash
cd backend
python -m app.seed --usuario-teste          # login "admin", senha "admin@123"
python -m app.seed --remover-usuario-teste  # remover depois dos testes
```

* **Modo local:** o login é `admin` com senha `admin@123`. O mesmo comando cria a coordenação de teste: login `coordenacao.teste`, senha `coord@123` (perfil coordenador).
* **Modo Supabase:** o Supabase Auth exige e-mail. O comando cadastra `PLAN_USUARIO_TESTE_EMAIL` (padrão `admin@teste.local`). Crie o mesmo e-mail em **Supabase → Authentication → Users → Add user**, com a senha `admin@123` e a opção *Auto Confirm User*.
* **Proteções:**
  * o comando **recusa** `PLAN_AMBIENTE=producao`;
  * enquanto o usuário existir, a API registra um alerta nos logs e `/api/saude` mostra `usuario_teste_ativo: true`.

## 8. Fluxo contínuo de publicação

1. Desenvolver e testar localmente ([README.md](README.md), [TESTING.md](TESTING.md)).
2. `git commit` e `git push` para uma branch. O GitHub Actions (`.github/workflows/ci.yml`) executa:
   * testes do backend com PostgreSQL;
   * verificação da API no formato da Vercel (sem OR-Tools, menos de 250 MB);
   * busca de segredos versionados;
   * build do frontend.
3. A Vercel cria um **Preview Deployment** para a branch ou o *pull request*, usando as variáveis de *Preview* (banco de homologação).
4. Validar o *preview*. Se houver migração nova, aplique-a primeiro no banco de homologação ([SUPABASE.md](SUPABASE.md#aplicar-migrações)).
5. Aplicar a migração no banco de **produção**, de forma manual e após backup. Depois, fazer o *merge* na *Production Branch*: a Vercel publica em produção e o worker é atualizado pelo auto-deploy.

> Migrações **não** são executadas automaticamente no build da Vercel. Isso é intencional: nenhuma alteração de esquema atinge produção sem revisão.

## 9. Logs e erros

* **Vercel → Project → Logs (Functions):** cada requisição gera uma linha `req=<id> MÉTODO /caminho -> status duração`. Erros 500 registram o *stack trace*, e o cliente recebe só uma mensagem genérica. O cabeçalho `X-Request-Id` permite cruzar a requisição com o log.
* **Worker:** logs do provedor (início e fim de cada job, órfãos recuperados, falhas).
* **Banco:** Supabase → Logs (Postgres / Auth).
* **Auditoria funcional:** tela *Auditoria*, com tentativas de alocação bloqueadas, execuções, publicações e acessos.

## 10. Limites a conhecer

| Limite | Valor | Efeito |
|---|---|---|
| Duração da função | `maxDuration: 60` em `vercel.json` (o máximo depende do plano Vercel) | Endpoints síncronos pesados, como indicadores de um período muito longo, devem caber nesse tempo; otimizações rodam no worker |
| Corpo da requisição | 4,5 MB na Vercel | Importação limitada a 4 MB por arquivo (`/api/auth/config` informa o limite); divida planilhas maiores |
| Tamanho da função | 250 MB | A API usa cerca de 137 MB, sem OR-Tools |
| Sistema de arquivos | só leitura | Nada é gravado em disco; prévias de importação ficam no banco |
