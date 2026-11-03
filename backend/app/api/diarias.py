"""Diárias (recursos extras) para instrutores em eventos e projetos: a supervisão registra, aprova/recusa e marca como paga."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Contexto, get_contexto, requer
from app.models import Instrutor

router = APIRouter(prefix="/api")


@router.get("/diarias")
def listar_diarias(status: str | None = None, instrutor_id: int | None = None, ctx: Contexto = Depends(requer("solicitacoes.aprovar")),
                   db: Session = Depends(get_db)):
    from app.services import diarias
    r = diarias.listar(db, status=status or None, instrutor_id=instrutor_id, unidades=ctx.unidades)
    q = select(Instrutor).where(Instrutor.ativo.is_(True))
    if ctx.unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(ctx.unidades or [-1]))
    r["instrutores"] = [{"id": i.id, "nome": i.nome, "matricula": i.matricula} for i in db.scalars(q.order_by(Instrutor.nome))]
    return r


@router.post("/diarias")
def criar_diaria(d: dict = Body(...), ctx: Contexto = Depends(requer("solicitacoes.aprovar")), db: Session = Depends(get_db)):
    from app.services import diarias
    s = diarias.criar(db, ctx, d)
    db.commit()
    return diarias.serializar(db, s)


@router.put("/diarias/{sid}")
def alterar_diaria(sid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("solicitacoes.aprovar")), db: Session = Depends(get_db)):
    from app.services import diarias
    s = diarias.alterar(db, ctx, sid, d)
    db.commit()
    return diarias.serializar(db, s)


@router.post("/diarias/{sid}/situacao")
def mudar_situacao_diaria(sid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("solicitacoes.aprovar")), db: Session = Depends(get_db)):
    """Aprovar, recusar (com motivo), marcar como paga ou cancelar."""
    from app.services import diarias
    s = diarias.decidir(db, ctx, sid, d.get("status") or "", d.get("resposta"), d.get("pago_em"))
    db.commit()
    return diarias.serializar(db, s)


@router.get("/portal/diarias")
def minhas_diarias(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """O instrutor acompanha as diárias solicitadas para ele (só leitura)."""
    from app.services import diarias
    iid = getattr(ctx.usuario, "instrutor_id", None)
    return diarias.listar(db, instrutor_id=iid)["itens"] if iid else []
