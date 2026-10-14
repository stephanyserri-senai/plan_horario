"""Aplicação FastAPI: Plataforma de Planejamento Acadêmico."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import analise, cadastros, planejamento, seguranca
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ErroDominio

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

if settings.producao and settings.jwt_secret.startswith("dev-"):
    raise RuntimeError("Defina PLAN_JWT_SECRET em produção.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.otimizacao import recuperar_execucoes_interrompidas
    try:
        with SessionLocal() as db:
            n = recuperar_execucoes_interrompidas(db)
            if n:
                log.warning("%s execução(ões) do otimizador interrompida(s) foram marcadas como falha.", n)
    except Exception:
        log.exception("Falha ao recuperar execuções interrompidas")
    yield


app = FastAPI(title="Plataforma de Planejamento Acadêmico", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origens.split(",")], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


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


for r in (seguranca.router, cadastros.router, planejamento.router, analise.router):
    app.include_router(r)


@app.get("/api/saude")
def saude():
    with SessionLocal() as db:
        db.execute(__import__("sqlalchemy").text("select 1"))
    return {"status": "ok", "ambiente": settings.ambiente}


# Em produção, o build do frontend é servido pela própria API.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str):
        alvo = _dist / caminho
        return FileResponse(alvo if caminho and alvo.is_file() else _dist / "index.html")
