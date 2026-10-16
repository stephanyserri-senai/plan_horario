"""EPIs: lista do curso (cadastro) e controle por turma (comprado/separado, entregue, prazo)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Contexto, get_contexto
from app.core.errors import NaoEncontrado
from app.models import Curso, EpiCurso, EpiTurma, Turma
from app.services import epis

router = APIRouter(prefix="/api", tags=["EPIs"])


def _curso(db: Session, ctx: Contexto, curso_id: int) -> Curso:
    c = db.get(Curso, curso_id)
    if c is None or (ctx.unidades is not None and c.unidade_id is not None and c.unidade_id not in ctx.unidades):
        raise NaoEncontrado("Curso não encontrado.")
    return c


@router.get("/cursos/{curso_id}/epis")
def epis_do_curso(curso_id: int, db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    _curso(db, ctx, curso_id)
    return [epis.ser_curso(e) for e in db.scalars(select(EpiCurso).where(EpiCurso.curso_id == curso_id, EpiCurso.ativo.is_(True)).order_by(EpiCurso.nome))]


@router.post("/cursos/{curso_id}/epis")
def incluir_epi(curso_id: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    _curso(db, ctx, curso_id)
    e = epis.criar_epi_curso(db, ctx, curso_id, dados)
    db.commit()
    return epis.ser_curso(e)


@router.put("/epis-curso/{eid}")
def alterar_epi(eid: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    e = db.get(EpiCurso, eid)
    if e is None:
        raise NaoEncontrado("EPI não encontrado.")
    _curso(db, ctx, e.curso_id)
    e = epis.alterar_epi_curso(db, ctx, eid, dados)
    db.commit()
    return epis.ser_curso(e)


@router.get("/epis-turmas")
def controle(turma_id: int | None = None, curso_id: int | None = None, situacao: str | None = None,
             db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.ler")
    return epis.listar(db, ctx.unidades, turma_id=turma_id, curso_id=curso_id, situacao_filtro=situacao)


@router.put("/epis-turmas/{eid}")
def marcar(eid: int, dados: dict = Body(...), db: Session = Depends(get_db), ctx: Contexto = Depends(get_contexto)):
    ctx.exigir("cadastros.editar")
    e = db.get(EpiTurma, eid)
    t = db.get(Turma, e.turma_id) if e else None
    if t is None or (ctx.unidades is not None and t.unidade_id not in ctx.unidades):
        raise NaoEncontrado("EPI da turma não encontrado.")
    epis.marcar(db, ctx, eid, dados)
    db.commit()
    return next((i for i in epis.listar(db, ctx.unidades, turma_id=t.id)["itens"] if i["id"] == eid), None)
