"""Agendamento de ambientes: grade de disponibilidade (ambientes × dias × turnos), pedidos do instrutor pelo portal e
confirmação/recusa pela supervisão (que também agenda direto)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Contexto, get_contexto, requer
from app.core.errors import EntradaInvalida, NaoEncontrado
from app.models import AgendamentoAmbiente, Ambiente, Instrutor, InstrutorUnidade, TipoAmbiente, Unidade

router = APIRouter(prefix="/api")


def _semana(inicio: date | None, fim: date | None) -> tuple[date, date]:
    from app.services.agendamentos import hoje
    ini = inicio or (hoje() - timedelta(days=hoje().weekday()))
    return ini, fim or ini + timedelta(days=5)


def _filtros(db: Session, unidades: list[int]) -> dict:
    return {"unidades": [{"id": u.id, "nome": u.nome} for u in db.scalars(select(Unidade).where(Unidade.id.in_(unidades)).order_by(Unidade.nome))],
            "tipos": [{"id": t.id, "nome": t.nome} for t in db.scalars(select(TipoAmbiente).order_by(TipoAmbiente.nome))]}


# ----------------------------------------------------------------------------- supervisão / equipe
@router.get("/ambientes/agenda")
def agenda_ambientes(unidade_id: int | None = None, inicio: date | None = None, fim: date | None = None, area_id: int | None = None,
                     tipo_ambiente_id: int | None = None, q: str | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")),
                     db: Session = Depends(get_db)):
    """Disponibilidade dos ambientes por dia e turno (a antiga planilha de agendamento)."""
    from app.services import agendamentos
    unidades = sorted(ctx.unidades) if ctx.unidades is not None else [u.id for u in db.scalars(select(Unidade).where(Unidade.ativo.is_(True)))]
    if not unidades:
        raise NaoEncontrado("Nenhuma unidade no seu acesso.")
    uid = unidade_id if unidade_id in unidades else unidades[0]
    ini, f = _semana(inicio, fim)
    return {**agendamentos.grade(db, ini, f, uid, area_id, tipo_ambiente_id, q), **_filtros(db, unidades)}


@router.get("/agendamentos")
def listar_agendamentos(status: str | None = None, ctx: Contexto = Depends(requer("alocacoes.ler")), db: Session = Depends(get_db)):
    from app.services import agendamentos
    return agendamentos.listar(db, status=status, unidades=ctx.unidades, desde=agendamentos.hoje() - timedelta(days=30))


@router.post("/agendamentos")
def agendar_direto(d: dict = Body(...), ctx: Contexto = Depends(requer("solicitacoes.aprovar")), db: Session = Depends(get_db)):
    """Supervisão agenda um ambiente (já confirmado), para um instrutor ou para a própria equipe."""
    from app.services import agendamentos
    amb = db.get(Ambiente, int(d.get("ambiente_id") or 0))
    if amb is None:
        raise NaoEncontrado("Ambiente não encontrado.")
    ctx.exigir_unidade(amb.unidade_id)
    inst = db.get(Instrutor, int(d["instrutor_id"])) if d.get("instrutor_id") else None
    g = agendamentos.criar(db, ctx, amb.id, d.get("data"), d.get("turno_id"), d.get("finalidade") or "", inst, d.get("turma_id"),
                           d.get("participantes"), confirmar_ja=True)
    db.commit()
    return agendamentos.serializar(db, g)


@router.put("/agendamentos/{gid}")
def decidir_agendamento(gid: int, d: dict = Body(...), ctx: Contexto = Depends(requer("solicitacoes.aprovar")), db: Session = Depends(get_db)):
    """{"status": "confirmado" | "recusado", "resposta"?}: confirmar vira bloqueio do ambiente; o instrutor é avisado."""
    from app.services import agendamentos
    g = db.get(AgendamentoAmbiente, gid)
    if g is not None:
        ctx.exigir_unidade(db.get(Ambiente, g.ambiente_id).unidade_id)
    g = agendamentos.decidir(db, ctx, gid, d.get("status") or "", d.get("resposta"))
    db.commit()
    return agendamentos.serializar(db, g)


@router.post("/agendamentos/{gid}/cancelar")
def cancelar_agendamento(gid: int, d: dict = Body(default={}), ctx: Contexto = Depends(requer("solicitacoes.aprovar")),
                         db: Session = Depends(get_db)):
    from app.services import agendamentos
    g = agendamentos.cancelar(db, ctx, gid, None, (d or {}).get("motivo"))
    db.commit()
    return agendamentos.serializar(db, g)


# ----------------------------------------------------------------------------- portal do instrutor
def _eu(ctx: Contexto, db: Session) -> Instrutor:
    from app.api.portal import _meu_instrutor
    return _meu_instrutor(ctx, db)


@router.get("/portal/ambientes/agenda")
def minha_agenda_ambientes(unidade_id: int | None = None, inicio: date | None = None, fim: date | None = None, area_id: int | None = None,
                           tipo_ambiente_id: int | None = None, q: str | None = None, ctx: Contexto = Depends(get_contexto),
                           db: Session = Depends(get_db)):
    """Ambientes das unidades em que o instrutor atua, com os horários livres para pedir."""
    from app.services import agendamentos
    inst = _eu(ctx, db)
    unidades = sorted({inst.unidade_id, *db.scalars(select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == inst.id))})
    uid = unidade_id if unidade_id in unidades else inst.unidade_id
    ini, f = _semana(inicio, fim)
    r = agendamentos.grade(db, ini, f, uid, area_id, tipo_ambiente_id, q)
    # no portal, o nome de quem reservou só aparece nos pedidos do próprio instrutor
    for a in r["ambientes"]:
        for c in a["celulas"].values():
            if c["estado"] in ("reservado", "pendente") and c.get("instrutor_id") != inst.id:
                c["texto"] = "reservado" if c["estado"] == "reservado" else "aguardando"
            c["meu"] = c.get("instrutor_id") == inst.id
            c.pop("instrutor_id", None)
    return {**r, **_filtros(db, unidades), "area_padrao": inst.area_id}


@router.get("/portal/agendamentos")
def meus_agendamentos(ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    from app.services import agendamentos
    inst = _eu(ctx, db)
    return agendamentos.listar(db, instrutor_id=inst.id, desde=agendamentos.hoje() - timedelta(days=30))


@router.post("/portal/agendamentos")
def pedir_ambiente(d: dict = Body(...), ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    """Pede um ambiente num dia e turno livre; fica aguardando a supervisão (e já segura o horário)."""
    from app.services import agendamentos
    inst = _eu(ctx, db)
    amb = db.get(Ambiente, int(d.get("ambiente_id") or 0))
    unidades = {inst.unidade_id, *db.scalars(select(InstrutorUnidade.unidade_id).where(InstrutorUnidade.instrutor_id == inst.id))}
    if amb is None or amb.unidade_id not in unidades:
        raise EntradaInvalida("Escolha um ambiente de uma unidade em que você atua.")
    g = agendamentos.criar(db, ctx, amb.id, d.get("data"), d.get("turno_id"), d.get("finalidade") or "", inst, d.get("turma_id"), d.get("participantes"))
    db.commit()
    return agendamentos.serializar(db, g)


@router.post("/portal/agendamentos/{gid}/cancelar")
def cancelar_meu_agendamento(gid: int, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)):
    from app.services import agendamentos
    g = agendamentos.cancelar(db, ctx, gid, _eu(ctx, db))
    db.commit()
    return agendamentos.serializar(db, g)
