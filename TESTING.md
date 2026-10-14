# Testes e validações antes da publicação

## 1. Testes automatizados (backend)

Os testes usam **PostgreSQL real**, porque *exclusion constraints*, *advisory locks*, transações, RLS e a fila fazem parte do que é testado. Cada teste trunca as tabelas do banco de testes; **nunca** aponte para um banco com dados reais.

```bash
createdb plan_horario_test        # ou um projeto Supabase descartável
cd backend
pip install -r requirements.txt
PLAN_TEST_DATABASE_URL=postgresql+psycopg://plan:plan@localhost:5432/plan_horario_test python -m pytest -q
```

| Arquivo | O que cobre |
|---|---|
| `test_conflitos.py` | Regras obrigatórias (sala, instrutor, turma, grupos, capacidade, habilitação, disponibilidade, bloqueios, sobreposição parcial, carga horária, equipamentos, jornada). Reservas **concorrentes com threads reais** e *exclusion constraints* sem a camada de serviço. Integridade após falha de transação e versão otimista |
| `test_otimizacao.py` | Solver: viável/ótimo, comprovadamente inviável, limite de tempo sem prova, aulas fixas preservadas, recuperação de execução interrompida |
| `test_cenarios_indicadores.py` | Ocupação por turno, carga dos instrutores, indicadores após mudança, versões, publicação, propostas e simulador sem alterar o vigente |
| `test_importacao_api.py` | Importação duplicada e referências inválidas, autorização e escopo, fluxo completo via API e exportações |
| `test_deploy.py` | **Preparação Vercel/Supabase**, detalhada abaixo |

O que `test_deploy.py` verifica:
* normalização de URLs do Supabase;
* NullPool e ausência de *prepared statements* no pooler 6543;
* validação de configuração em produção;
* `requirements.txt` da Vercel sem OR-Tools e idêntico ao `backend/requirements-api.txt`;
* **API importável sem OR-Tools** (`VERCEL=1`);
* `/api/saude`;
* **RLS habilitado em todas as tabelas e papéis `anon`/`authenticated` sem acesso**, com papéis simulados e privilégios padrão do Supabase;
* **SQL offline das migrações** cria um banco novo;
* **fila processada pelo worker**, **dois workers nunca pegam o mesmo job** e recuperação por *heartbeat*;
* simulação via fila;
* prévia de importação persistida no banco;
* **Supabase Auth**: vínculo por e-mail, 403 sem cadastro, tokens expirados, de outra audiência, de outro emissor, mal assinados ou com `alg: none`, e ES256 via JWKS;
* segredos ausentes de `/api/auth/config`;
* usuário de teste recusado em produção.

## 2. Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

## 3. Verificações de formato serverless (equivalentes ao job `api-vercel` do CI)

```bash
python -m venv /tmp/v && /tmp/v/bin/pip install -r requirements.txt     # dependências da Vercel
VERCEL=1 /tmp/v/bin/python -c "import api.index; import importlib.util as u; assert u.find_spec('ortools') is None"
du -sm /tmp/v/lib/python3*/site-packages                                  # deve ficar bem abaixo de 250 MB (~137 MB)
```

Para simular a função localmente (API em modo fila, sem OR-Tools) e o worker separado:

```bash
VERCEL=1 /tmp/v/bin/pip install uvicorn && VERCEL=1 /tmp/v/bin/uvicorn api.index:app --port 8100   # API "Vercel"
cd backend && python -m app.worker --uma-vez                                                       # worker com OR-Tools
```

## 4. Validação em Preview

Antes de promover para produção, num **Preview Deployment** apontando para o banco de **homologação**:

1. `GET /api/saude` → `status: ok`, `migracao: 0002`, `auth: supabase`, `executor: fila` e `worker.estado` igual a `ocioso` ou `executando`, com horário recente.
2. Login:
   * com um usuário convidado;
   * com um e-mail **não** cadastrado na plataforma (deve aparecer a mensagem de acesso negado);
   * "Esqueci minha senha" (o link volta para o site).
3. Perfis: um usuário `consulta` não consegue criar aula (403); um planejador restrito a outra unidade não vê dados da unidade.
4. Cadastros: criar, editar e inativar um registro de teste, e conferir o histórico.
5. Grade: criar uma aula válida; tentar uma conflitante (o sistema deve bloquear, explicar e sugerir alternativas). Em duas abas, alterar a mesma aula: a segunda deve receber "alterada por outro usuário".
6. Geração inteligente:
   * executar num cenário **copiado**: o status passa de *na fila* para *concluída*, com aulas geradas;
   * validar o cenário (0 bloqueios);
   * com o worker parado, a execução deve ficar *na fila*. Ao religá-lo, é processada.
7. Simulador:
   * simulação agregada (imediata);
   * simulação completa (processada pelo worker), conferindo que o cenário publicado não mudou.
8. Importação:
   * arquivo de até 4 MB, com prévia, remapeamento e confirmação;
   * reimportar o mesmo arquivo (deve aparecer "já processado", sem duplicação).
9. Exportações XLSX, CSV e PDF.
10. Dashboard e gargalos carregam dentro do tempo limite.
11. Logs da Vercel e do worker sem erros 500 inesperados.
12. Remover o usuário de teste (`python -m app.seed --remover-usuario-teste`), se tiver sido criado.

## 5. Antes de cada publicação em produção

* [ ] CI verde (backend, api-vercel, frontend).
* [ ] Migrações novas aplicadas e verificadas em homologação; backup da produção feito; migração aplicada na produção.
* [ ] Variáveis de **Production** revisadas: `PLAN_AMBIENTE=producao`, banco de produção, Supabase de produção.
* [ ] Worker de produção atualizado e com `ocioso` em `/api/saude`.
* [ ] `usuario_teste_ativo: false` em `/api/saude` na produção.
