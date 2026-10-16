"""Aplicação FastAPI: Plataforma de Planejamento Acadêmico.

Roda de três formas, com o mesmo código:
- local (uvicorn): API + frontend compilado, otimizador em threads;
- Vercel (função Python serverless, api/index.py): somente API; otimizador
  em worker externo (PLAN_EXECUTOR=fila);
- container (Dockerfile): API completa ou worker (python -m app.worker).
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from app.api import analise, cadastros, epis, planejamento, seguranca, portal
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ErroDominio

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

_erros_config = settings.validar()
if _erros_config:
    # Falha cedo e de forma explícita: configuração insegura ou incompleta.
    raise RuntimeError("Configuração inválida: " + " | ".join(_erros_config))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Recuperação de execuções interrompidas só faz sentido quando ESTE processo
    # executa o otimizador (modo thread). Em serverless/fila, o worker faz a
    # recuperação baseada em heartbeat — senão cada cold start derrubaria jobs vivos.
    if settings.modo_executor == "thread":
        from app.services.otimizacao import recuperar_execucoes_interrompidas
        try:
            with SessionLocal() as db:
                n = recuperar_execucoes_interrompidas(db)
                if n:
                    log.warning("%s execução(ões) do otimizador interrompida(s) foram marcadas como falha.", n)
        except Exception:
            log.exception("Falha ao recuperar execuções interrompidas")
    try:
        from app.seed import usuario_teste_ativo
        with SessionLocal() as db:
            if usuario_teste_ativo(db):
                log.warning("ATENÇÃO: o usuário de TESTE (admin/admin@123) está ativo. Remova-o antes da produção: python -m app.seed --remover-usuario-teste")
    except Exception:
        log.debug("Verificação do usuário de teste não realizada", exc_info=True)
    log.info("API iniciada (ambiente=%s, auth=%s, executor=%s, serverless=%s)", settings.ambiente, settings.auth_modo,
             settings.modo_executor, settings.serverless)
    yield


app = FastAPI(title="Plataforma de Planejamento Acadêmico", version="1.1.0", lifespan=lifespan,
              docs_url=None if settings.producao else "/api/docs", openapi_url=None if settings.producao else "/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origens.split(",") if o.strip()], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def registrar_requisicao(request: Request, call_next):
    """Log estruturado por requisição (visível nos logs da Vercel/worker) e
    cabeçalhos de segurança. Não registra corpo nem tokens."""
    rid = request.headers.get("x-vercel-id") or uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    try:
        resposta = await call_next(request)
    except Exception:
        log.exception("req=%s %s %s falhou", rid, request.method, request.url.path)
        raise
    dur = (time.perf_counter() - t0) * 1000
    nivel = logging.WARNING if resposta.status_code >= 500 or dur > 10000 else logging.INFO
    if request.url.path.startswith("/api"):
        log.log(nivel, "req=%s %s %s -> %s %.0fms", rid, request.method, request.url.path, resposta.status_code, dur)
    resposta.headers["X-Request-Id"] = rid
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/api"):
        resposta.headers.setdefault("Cache-Control", "no-store")
    return resposta


@app.exception_handler(ErroDominio)
async def erro_dominio(request: Request, exc: ErroDominio):
    return JSONResponse(status_code=exc.status, content={"erro": exc.mensagem, "codigo": exc.codigo, "detalhes": exc.detalhes})


@app.exception_handler(RequestValidationError)
async def erro_validacao(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"erro": "Requisição inválida.", "codigo": "REQUISICAO_INVALIDA",
                                                  "detalhes": [{"campo": ".".join(map(str, e["loc"])), "mensagem": e["msg"]} for e in exc.errors()]})


@app.exception_handler(Exception)
async def erro_interno(request: Request, exc: Exception):
    log.exception("Erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"erro": "Erro interno. A operação foi desfeita.", "codigo": "ERRO_INTERNO"})


for r in (seguranca.router, cadastros.router, planejamento.router, analise.router, portal.router, epis.router):
    app.include_router(r)


DICAS_BANCO = [
    ("password authentication failed", "Senha do banco incorreta em PLAN_DATABASE_URL (use a senha do banco definida ao criar o projeto, sem colchetes)."),
    ("tenant or user not found", "Usuário ou host do pooler incorretos: o usuário deve ser 'postgres.<ref-do-projeto>' e o host o do pooler copiado em Supabase → Connect."),
    ("could not translate host name", "Host do banco inválido: copie novamente a URL em Supabase → Connect → Transaction pooler."),
    ("name or service not known", "Host do banco inválido: copie novamente a URL em Supabase → Connect → Transaction pooler."),
    ("network is unreachable", "Rede inalcançável (a conexão direta do Supabase é só IPv6): use a URL do pooler (porta 6543)."),
    ("connection refused", "Conexão recusada: host/porta incorretos (Vercel deve usar o Transaction pooler, porta 6543)."),
    ("timeout", "Tempo esgotado ao conectar: confira host e porta (6543 para o Transaction pooler)."),
    ("timed out", "Tempo esgotado ao conectar: confira host e porta (6543 para o Transaction pooler)."),
    ("does not exist", "Banco/tabela inexistente: confira o nome do banco (postgres) e se as migrações foram aplicadas."),
    ("plan_database_url inválida", "A senha na URL ainda tem colchetes '[ ]' (remova os de [YOUR-PASSWORD]) ou caracteres especiais não codificados."),
    ("ssl", "Problema de SSL: a URL do Supabase deve usar SSL (a aplicação adiciona sslmode=require automaticamente)."),
]


def _diagnostico_banco(exc: Exception) -> dict:
    """Diagnóstico da conexão SEM expor a senha. Detalhes só fora da produção."""
    import re
    from urllib.parse import unquote
    bruto = str(getattr(exc, "orig", None) or exc)
    # análise tolerante (urlsplit falha com '[' na senha)
    m = re.match(r"^[a-z+]+://(?P<usuario>[^:@/]*)(?::(?P<senha>.*))?@(?P<host>[^:/?]+)(?::(?P<porta>\d+))?/(?P<banco>[^?]*)", settings.database_url.strip())
    g = m.groupdict() if m else {}
    senha = unquote(g.get("senha") or "")
    if senha:
        bruto = bruto.replace(senha, "***")
    msg = bruto.split("(Background on this error")[0].strip()[:500]
    info = {"status": "erro", "componente": "banco_de_dados", "erro_tipo": type(getattr(exc, "orig", None) or exc).__name__}
    if settings.producao:
        return info
    baixo = msg.lower()
    info.update({
        "mensagem": msg,
        "dica": next((d for k, d in DICAS_BANCO if k in baixo), "Confira a variável PLAN_DATABASE_URL na Vercel e faça um novo deploy (Redeploy)."),
        "conexao_configurada": {
            "variavel_lida": "PLAN_DATABASE_URL" if __import__("os").environ.get("PLAN_DATABASE_URL") else
                             ("DATABASE_URL/POSTGRES_URL" if settings.database_url else "nenhuma"),
            "url_reconhecida": bool(m),
            "host": g.get("host"), "porta": int(g["porta"]) if g.get("porta") else None, "usuario": g.get("usuario"), "banco": g.get("banco"),
            "senha_preenchida": bool(senha), "senha_com_colchetes": senha.startswith("[") or "YOUR-PASSWORD" in senha.upper(),
            "url_com_espacos": settings.database_url != settings.database_url.strip(),
        },
    })
    return info


@app.get("/api/saude")
def saude():
    """Diagnóstico sem dados sensíveis: banco, migração, modo de execução e fila."""
    from app.models import Configuracao, ExecucaoOtimizacao, SimulacaoCapacidade
    base = {"ambiente": settings.ambiente, "auth": settings.auth_modo, "executor": settings.modo_executor}
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
    except Exception as e:
        log.exception("Falha ao conectar ao banco em /api/saude")
        return JSONResponse(status_code=503, content={**base, **_diagnostico_banco(e)})
    try:
        with SessionLocal() as db:
            try:
                revisao = db.scalar(text("select version_num from alembic_version"))
            except Exception:
                db.rollback()
                revisao = None
            fila = {
                "execucoes_pendentes": db.scalar(select(func.count()).select_from(ExecucaoOtimizacao).where(ExecucaoOtimizacao.status == "pendente")),
                "simulacoes_pendentes": db.scalar(select(func.count()).select_from(SimulacaoCapacidade).where(SimulacaoCapacidade.status == "pendente")),
            }
            w = db.get(Configuracao, "worker_status")
            from app.seed import usuario_teste_ativo
            teste = usuario_teste_ativo(db)
    except Exception as e:
        log.exception("Falha nas consultas de /api/saude")
        info = _diagnostico_banco(e)
        info["componente"] = "consultas (banco conectado; verifique se as migrações foram aplicadas)"
        return JSONResponse(status_code=503, content={**base, **info})
    return {"usuario_teste_ativo": teste, "status": "ok", **base, "migracao": revisao, "fila": fila, "worker": w.valor if w else None}


# Fora da Vercel, o build do frontend é servido pela própria API (na Vercel, pela CDN).
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists() and not settings.serverless:
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str):
        alvo = (_dist / caminho).resolve()
        if caminho and alvo.is_file() and _dist.resolve() in alvo.parents:
            return FileResponse(alvo)
        return FileResponse(_dist / "index.html")
