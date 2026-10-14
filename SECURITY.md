# Segurança e permissões

## Segredos e variáveis de ambiente

| Tipo | Exemplos | Onde pode estar |
|---|---|---|
| **Segredos de servidor** | `PLAN_DATABASE_URL` (contém a senha do banco), `PLAN_JWT_SECRET`, `PLAN_SUPABASE_JWT_SECRET`, `PLAN_SUPABASE_SERVICE_ROLE_KEY` | variáveis de ambiente da Vercel e do worker; cofre de senhas. **Nunca** no repositório nem no frontend |
| **Públicas** | `PLAN_SUPABASE_URL`, `PLAN_SUPABASE_ANON_KEY` | entregues ao navegador por `GET /api/auth/config`. A chave anon não dá acesso a dados (RLS + revogação) |

* `.env`, `.env.*` (exceto `.env.example`), `.vercel/`, `backups/`, `*.dump`, `*.pem` e `*.key` estão no `.gitignore`. O `.vercelignore` e o `backend/.dockerignore` excluem `.env*` dos envios.
* O frontend não usa variáveis `VITE_*`. Nenhum segredo é embutido no build.
* `GET /api/auth/config` só devolve o modo de autenticação, a URL do projeto e a chave pública. Um teste automatizado garante que segredos não aparecem nessa resposta.
* O CI procura arquivos `.env` versionados e padrões de chaves JWT/`service_role` no código.
* Se algum segredo for exposto: **revogue e gere outro** (senha do banco, chaves de API e segredo JWT no Supabase; `PLAN_JWT_SECRET` na Vercel) e faça um novo deploy. Apagar o commit não basta.

## Autenticação

* **Modo Supabase** (recomendado em produção):
  * o access token do Supabase Auth é validado **no servidor** em cada requisição: assinatura (JWKS RS256/ES256 ou segredo HS256), expiração, emissor e audiência `authenticated`;
  * tokens com `alg: none`, outra audiência, outro emissor ou assinatura inválida são recusados (testes em `test_deploy.py`);
  * um login válido no Supabase **não** dá acesso sozinho: o e-mail precisa estar cadastrado e ativo na plataforma (senão, 403);
  * o cadastro público (sign up) deve ficar desativado no Supabase.
* **Modo local:** senhas com bcrypt, JWT HS256 com expiração (`PLAN_JWT_EXPIRA_MINUTOS`). Em produção, a API não inicia com `PLAN_JWT_SECRET` fraco (menos de 32 caracteres ou o valor de desenvolvimento).
* **Usuário de teste** (`admin` / `admin@123`):
  * criado apenas por comando explícito (`python -m app.seed --usuario-teste`);
  * **recusado** com `PLAN_AMBIENTE=producao`;
  * gera alerta nos logs e aparece em `/api/saude` enquanto ativo;
  * remova com `python -m app.seed --remover-usuario-teste`.

## Autorização

* Perfis (administrador, planejador, coordenador, gestor, consulta) e ações configuráveis (tabela `permissoes_perfil`), além de escopo por unidade, curso ou turma (tabela `permissoes`). **Tudo é validado no servidor**; o frontend apenas oculta botões.
* Usuários sem acesso global e sem escopo não veem dados de nenhuma unidade.
* Dados pessoais de instrutores (e-mail) só são exibidos com a permissão `dados_pessoais.ler`.
* Exportações exigem `exportacao.executar` e são auditadas.
* Nenhum erro de permissão é "resolvido" com credenciais administrativas: a API usa o papel dono das tabelas, mas toda operação passa pelo perfil e escopo do usuário autenticado.

## Banco de dados

* **RLS habilitado em todas as tabelas** e privilégios revogados dos papéis `anon`/`authenticated` (migração 0002). A Data API do Supabase não expõe dados, nem com a chave pública.
* Conexões ao Supabase com `sslmode=require`.
* Integridade e concorrência garantidas no banco:
  * *exclusion constraints* impedem sobreposição de instrutor, ambiente e turma/grupo;
  * `pg_advisory_xact_lock` protege as regras de carga horária, jornada e equipamentos;
  * versão otimista (`versao`/`lock_version`) evita sobrescrever alterações de outro usuário;
  * fila com `FOR UPDATE SKIP LOCKED` evita que dois workers peguem o mesmo job.
* Auditoria gravada na mesma transação da operação.

## Entradas e respostas

* Validação de tipos e regras no servidor. Erros de domínio retornam mensagens claras; erros internos retornam mensagem genérica, com detalhes só nos logs.
* Upload limitado: 4 MB na Vercel, 20 MB fora dela. O arquivo da prévia é apagado após confirmar ou descartar a importação.
* Cabeçalhos de segurança: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` e HSTS (via `vercel.json`). Respostas da API usam `Cache-Control: no-store`.
* A documentação interativa da API (`/api/docs`) fica desativada em produção.
* O fallback de arquivos estáticos (uso fora da Vercel) bloqueia *path traversal*.
* CORS: na Vercel, frontend e API têm a mesma origem. `PLAN_CORS_ORIGENS` só é necessário para outros domínios. Não se usam cookies de sessão; o token vai no cabeçalho `Authorization`.

## Pontos de atenção (riscos conhecidos)

* **Sem limite de tentativas no login do modo local.** Em produção, use o modo Supabase, que tem proteção própria, ou adicione *rate limiting* na borda (Vercel Firewall).
* **Sessão no navegador:** o token fica no `localStorage` (modo local) ou no armazenamento do supabase-js. Proteja contra XSS: a interface não usa `dangerouslySetInnerHTML`. Mantenha as dependências atualizadas.
* **Usuários do Supabase sem cadastro** na plataforma não acessam nada, mas desative o *sign up* para evitar contas órfãs.
* Revise periodicamente a tela **Usuários e permissões**, os logs de auditoria (`auth.falha`, `usuario.*`, `perfil.alterar`) e o **Security Advisor** do Supabase.

## Relato de vulnerabilidades

Comunique problemas de segurança diretamente aos mantenedores do repositório, sem abrir *issue* pública com detalhes exploráveis.
