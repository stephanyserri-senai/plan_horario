# Supabase: banco de dados, autenticação e migrações

## 1. Projetos e ambientes

Crie **um projeto Supabase por ambiente**:

| Ambiente | Projeto Supabase | Usado por |
|---|---|---|
| Desenvolvimento | PostgreSQL local (`docker compose up -d db`) ou um projeto `plan-dev` | sua máquina |
| Homologação | `plan-homologacao` | Vercel **Preview** + worker de homologação |
| Produção | `plan-producao` | Vercel **Production** + worker de produção |

* Nunca aponte *previews* para o banco de produção.
* Escolha a região mais próxima dos usuários (ex.: `sa-east-1`, São Paulo) e a **mesma** região para o worker.
* Ative o **Point-in-Time Recovery** (planos pagos) no projeto de produção.

## 2. Criar o projeto

1. <https://supabase.com/dashboard> → **New project** → defina o nome, uma **senha forte do banco** (guarde num cofre de senhas) e a região.
2. Em **Project Settings → Data API**, anote:
   * **Project URL** → `PLAN_SUPABASE_URL`;
   * chave **anon/publishable** → `PLAN_SUPABASE_ANON_KEY` (pública).
3. Em **Project Settings → JWT Keys** (ou *API → JWT Settings* em projetos antigos):
   * se o projeto usa **chaves de assinatura assimétricas** (padrão em projetos novos), nada a fazer: a API valida os tokens pelo JWKS público `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`;
   * se usa o **segredo JWT legado (HS256)**, copie-o para `PLAN_SUPABASE_JWT_SECRET` (segredo do servidor).
4. Opcional: a chave **service_role/secret** → `PLAN_SUPABASE_SERVICE_ROLE_KEY`, **somente** no servidor, para enviar convites pela tela de usuários.

## 3. Strings de conexão (**Connect** no topo do painel)

| Uso | Tipo | Porta | Variável |
|---|---|---|---|
| API na Vercel (serverless) | **Transaction pooler** | 6543 | `PLAN_DATABASE_URL` (Vercel) |
| Worker (processo contínuo) | **Session pooler** ou *Direct connection* | 5432 | `PLAN_DATABASE_URL` (worker) |
| Migrações (Alembic) | **Session pooler** ou *Direct connection* | 5432 | `PLAN_DATABASE_URL_MIGRACOES` ou `ALEMBIC_DATABASE_URL` |

* A conexão direta (`db.<ref>.supabase.co`) usa apenas IPv6. Em redes só IPv4, use o *Session pooler*.
* A aplicação aceita a URL como o Supabase a fornece (`postgres://` ou `postgresql://`): converte para o driver psycopg 3 e força `sslmode=require` em hosts do Supabase.
* Em modo transação (6543), a aplicação desativa *prepared statements* e o *pool* local (NullPool), como exige o Supavisor.
* O controle de concorrência usa apenas recursos de **escopo de transação**: `pg_advisory_xact_lock`, `SELECT … FOR UPDATE [SKIP LOCKED]` e *exclusion constraints*. Por isso ele é compatível com o pooler.
* Senhas com caracteres especiais devem ir codificadas na URL (ex.: `@` → `%40`).

## 4. Aplicar migrações

As migrações são versionadas no GitHub em `backend/alembic/versions/` e o **Alembic é a fonte da verdade**:

* `0001_esquema_inicial`: tabelas, chaves, índices, *check constraints* e as *exclusion constraints* GiST que impedem conflitos de instrutor, ambiente e turma/grupo. Cria as extensões `btree_gist` e `intarray`.
* `0002_supabase_vercel`: vínculo com o Supabase Auth, fila de jobs, conteúdo da importação, **RLS habilitado em todas as tabelas** e revogação de privilégios dos papéis `anon`/`authenticated`. É **não destrutiva**: só adiciona colunas anuláveis e índices.

### Aplicar migrações

```bash
cd backend
pip install -r requirements.txt
export ALEMBIC_DATABASE_URL='postgresql://postgres.<ref>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres'

python -m alembic current          # revisão atual (vazio = banco novo)
python -m alembic upgrade head --sql | less   # (opcional) revise o SQL antes
python -m alembic upgrade head     # aplica
python -m alembic current          # deve mostrar 0002 (head)
```

**Ordem segura para produção:**

1. Faça backup (seção 8).
2. Aplique em **homologação** e valide o *preview*.
3. Aplique em **produção**.

As migrações rodam em transação: se falharem, nada é alterado. **Nunca** rode `alembic downgrade` em produção sem backup e revisão, pois um *downgrade* pode remover colunas.

**Alternativa sem Python (SQL Editor do Supabase), para banco NOVO:**

1. cole e execute `backend/sql/schema_completo.sql` (estrutura completa; gerado por `scripts/gerar_sql_migracoes.sh`);
2. cole e execute `backend/sql/seed_inicial.sql`. Ele traz perfis, pesos padrão e configurações e é idempotente. Também cria o **usuário de teste** `admin` / `admin@123` (apenas homologação; o `DELETE` para removê-lo está no próprio arquivo). É gerado por `scripts/gerar_seed_sql.py`.

Para bancos que já têm dados, use o Alembic.

**Atualizar um banco que já está na versão 0002 (ex.: homologação) pelo SQL Editor:** cole e execute, nesta ordem, `backend/sql/atualizacao_0003.sql` (unidades Beira Mar e Porto, áreas tecnológicas, turnos oficiais e coluna de área nos cadastros) `backend/sql/atualizacao_0004.sql` (áreas múltiplas e exceção justificada de regra acadêmica) e `backend/sql/atualizacao_0005.sql` (portal do instrutor: perfil `instrutor`, vínculo usuário × instrutor e observações dos instrutores). Todas são não destrutivas. Opcional: `backend/sql/remover_unidade_teste.sql` remove uma unidade de teste vazia (código `TESTE`).

**Dados de demonstração pelo SQL Editor (homologação):** cole e execute `backend/sql/demo_recarregar.sql`. Ele remove só os registros `DEMO-` (incluindo o cenário DEMO e suas aulas), carrega a demonstração atual e registra a regra de composição das aulas (`regras_aula`) se ainda não existir. Pode ser executado mais de uma vez. É gerado por `scripts/gerar_demo_sql.py` (equivale ao workflow "Dados de demonstração" → recarregar).

### Verificar o resultado

No **SQL Editor**:

```sql
select version_num from alembic_version;                     -- 0002
select conname from pg_constraint where conname like 'excl_alocacao_%';  -- 3 linhas
select relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity; -- 0 linhas (RLS em todas)
select has_table_privilege('anon', 'public.usuarios', 'select');           -- false
```

Ou pela API publicada: `GET /api/saude` deve retornar `"migracao": "0002"`.

### Extensões

`btree_gist` e `intarray` estão disponíveis no Supabase e são criadas pela migração 0001.
O Security Advisor pode apontar *"extension in public schema"*. É um aviso, não um erro.

Mover as extensões para o schema `extensions` exige recriar as *exclusion constraints*. Avalie isso com cuidado e só com backup.

### Novas migrações

1. Crie a migração com `alembic revision --autogenerate -m "descricao"` e **revise** o arquivo gerado.
2. Toda tabela nova precisa de `ALTER TABLE … ENABLE ROW LEVEL SECURITY`. O teste `test_rls_habilitado_e_papeis_publicos_sem_acesso` falha se alguma ficar sem.
3. Regenere `backend/sql/schema_completo.sql` com `scripts/gerar_sql_migracoes.sh`.

## 5. Dados iniciais e primeiro administrador

```bash
cd backend
export PLAN_DATABASE_URL='<session pooler ou conexão direta>'
export PLAN_AUTH_MODO=supabase
export PLAN_ADMIN_EMAIL='seu.email@instituicao.edu.br'
python -m app.seed            # perfis, pesos padrão, configurações e o cadastro do administrador
```

Depois, crie o mesmo e-mail em **Authentication → Users → Add user**, de uma destas formas:

* *Send invitation*: o usuário define a senha pelo link;
* *Create new user*, com *Auto Confirm User*.

No primeiro login, a plataforma vincula o usuário do Supabase ao cadastro (`usuarios.auth_user_id`).

* `python -m app.seed` é idempotente e **não** apaga dados.
* Dados de demonstração (`python -m app.demo carregar`) são opcionais, têm o prefixo `DEMO-` e podem ser removidos com `python -m app.demo remover`. **Não** os carregue em produção.

## 6. Autenticação (Supabase Auth)

Configure `PLAN_AUTH_MODO=supabase` (Vercel e worker).

1. **Authentication → Providers → Email:** habilite. Desative **Allow new users to sign up**, porque o acesso é concedido por convite. Usuários que se cadastrarem sozinhos não teriam permissão na plataforma, mas é melhor bloquear.
2. **Authentication → URL Configuration:**
   * **Site URL:** a URL de produção (ex.: `https://seu-projeto.vercel.app`);
   * **Redirect URLs:** a URL de produção e o padrão dos previews (ex.: `https://*-sua-equipe.vercel.app/**`), além de `http://localhost:5173/**` para desenvolvimento.
3. **Authentication → Emails:** em produção, configure um SMTP próprio (o envio padrão do Supabase tem limite baixo e é só para testes). Revise os textos dos e-mails de convite e recuperação.
4. **Fluxo de acesso:**
   1. O administrador cadastra o usuário na tela **Usuários e permissões**, com perfil e escopo. Se `PLAN_SUPABASE_SERVICE_ROLE_KEY` estiver configurada, a plataforma envia o convite automaticamente; senão, convide pelo painel do Supabase.
   2. O usuário abre o link do convite, define a senha (tela "Definir senha") e entra.
   3. A cada requisição, a API valida o token: assinatura (JWKS ou HS256), expiração, emissor `https://<ref>.supabase.co/auth/v1` e audiência `authenticated`. Em seguida, aplica o perfil e o escopo da tabela `usuarios`.
   4. Login válido no Supabase **sem** cadastro na plataforma recebe **403**. Usuário inativo na plataforma recebe **401**.
5. **Recuperação de senha:** link "Esqueci minha senha" na tela de login (requer o redirecionamento configurado no item 2).

O modo `local` (usuários e senhas próprios, bcrypt + JWT) continua disponível para desenvolvimento e testes. Em produção, prefira `supabase`.

## 7. Row Level Security (RLS) — como a proteção está organizada

* O navegador **nunca** acessa tabelas diretamente: não há chamadas ao PostgREST/Data API. Todo acesso a dados passa pela API, que valida autenticação, perfil, escopo por unidade/curso/turma e regras de negócio no servidor.
* A migração 0002:
  * habilita **RLS em todas as tabelas** do schema `public`, **sem políticas** (ou seja, negação total para `anon` e `authenticated`);
  * **revoga** todos os privilégios desses papéis, inclusive os *default privileges* de tabelas futuras.

  Mesmo com a chave pública, ninguém lê ou escreve dados pela Data API.
* A API e o worker conectam com o papel dono das tabelas (o usuário da string de conexão), que não é afetado pelo RLS. Esse papel é credencial **de servidor** e nunca vai ao frontend.
* Opcional: em **Project Settings → Data API**, remova o schema `public` de *Exposed schemas* para desativar a Data API sobre ele.

## 8. Backup, recuperação e proteção dos dados

* **Backups automáticos:** o Supabase faz backups diários (a retenção depende do plano). Em produção, habilite o **PITR**.
* **Backup lógico manual** (antes de migrações ou cargas grandes):
  ```bash
  DATABASE_URL='<session pooler/direta>' scripts/backup.sh backups/
  ```
  O `pg_dump` deve ser da mesma versão principal do servidor ou mais nova.
* **Restauração** num projeto **novo** ou de homologação, nunca por cima da produção sem decisão explícita:
  ```bash
  pg_restore --no-owner --clean --if-exists -d "$DATABASE_URL" backups/plan_horario_AAAAMMDD_HHMMSS.dump
  ```
* Guarde os arquivos `.dump` fora do repositório. O `.gitignore` já bloqueia `backups/` e `*.dump`.
* A senha do banco e as chaves `service_role` devem ficar só em cofres de senha e nas variáveis do servidor.
* Restrinja o acesso ao painel do Supabase: membros da organização com papel mínimo necessário e MFA ativado.
* **Dados pessoais de instrutores:** apenas perfis com `dados_pessoais.ler` veem e-mails. As exportações são auditadas.
