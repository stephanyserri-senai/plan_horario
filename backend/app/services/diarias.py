"""Diárias (recursos extras) para instrutores em eventos e projetos.

A supervisão registra a solicitação para um instrutor (evento, projeto ou outro motivo), com período, local, número de
diárias (aceita meia diária), valor unitário e outros recursos (transporte, hospedagem, material...). Depois aprova ou
recusa (com motivo) e, aprovada, marca como paga. O instrutor é avisado no portal. Se ele tem aula no período, a
solicitação mostra quantas, para a supervisão providenciar a substituição.
Situações: solicitada → aprovada → paga; ou recusada; cancelada enquanto não paga.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflitoValidacao, EntradaInvalida, NaoEncontrado
from app.models import Alocacao, Instrutor, SolicitacaoDiaria
from app.services import auditoria
from app.services.notificacoes import notificar

MOTIVOS = {"evento": "Evento", "projeto": "Projeto", "outro": "Outro"}
STATUS = {"solicitada": "Solicitada", "aprovada": "Aprovada", "paga": "Paga", "recusada": "Recusada", "cancelada": "Cancelada"}
PROXIMOS = {"solicitada": ["aprovada", "recusada", "cancelada"], "aprovada": ["paga", "cancelada"], "paga": [], "recusada": [],
            "cancelada": []}


def _data(v, rotulo: str) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise EntradaInvalida(f"Informe a {rotulo}.")


def _num(v, rotulo: str, obrig: bool = False) -> Decimal | None:
    if v in (None, ""):
        if obrig:
            raise EntradaInvalida(f"Informe {rotulo}.")
        return None
    try:
        n = Decimal(str(v).replace(",", "."))
    except InvalidOperation:
        raise EntradaInvalida(f"{rotulo.capitalize()} inválido.")
    if n < 0:
        raise EntradaInvalida(f"{rotulo.capitalize()} não pode ser negativo.")
    return n


def aulas_no_periodo(db: Session, instrutor_id: int, d0: date, d1: date) -> int:
    return db.scalar(select(func.count()).select_from(Alocacao).where(
        Alocacao.instrutor_id == instrutor_id, Alocacao.status != "cancelada", Alocacao.data >= d0, Alocacao.data <= d1)) or 0


def serializar(db: Session, s: SolicitacaoDiaria) -> dict:
    inst = db.get(Instrutor, s.instrutor_id)
    qtd = float(s.quantidade)
    vu = float(s.valor_unitario) if s.valor_unitario is not None else None
    return {"id": s.id, "instrutor_id": s.instrutor_id, "instrutor": inst.nome if inst else None, "matricula": inst.matricula if inst else None,
            "motivo": s.motivo, "motivo_rotulo": MOTIVOS.get(s.motivo, s.motivo), "titulo": s.titulo, "descricao": s.descricao,
            "destino": s.destino, "data_inicio": s.data_inicio.isoformat(), "data_fim": s.data_fim.isoformat(),
            "dias": (s.data_fim - s.data_inicio).days + 1, "quantidade": qtd, "valor_unitario": vu,
            "valor_total": round(qtd * vu, 2) if vu is not None else None, "outros_recursos": s.outros_recursos,
            "centro_custo": s.centro_custo, "status": s.status, "status_rotulo": STATUS[s.status], "proximos": PROXIMOS.get(s.status, []),
            "resposta": s.resposta, "decidido_em": s.decidido_em.isoformat() if s.decidido_em else None,
            "pago_em": s.pago_em.isoformat() if s.pago_em else None, "criado_em": s.criado_em.isoformat() if s.criado_em else None,
            "aulas_no_periodo": aulas_no_periodo(db, s.instrutor_id, s.data_inicio, s.data_fim)}


def _preencher(db: Session, s: SolicitacaoDiaria, d: dict):
    inst = db.get(Instrutor, int(d.get("instrutor_id") or 0)) if d.get("instrutor_id") else None
    if inst is None:
        raise EntradaInvalida("Escolha o instrutor.")
    motivo = (d.get("motivo") or "").strip().lower()
    if motivo not in MOTIVOS:
        raise EntradaInvalida("Motivo: evento, projeto ou outro.")
    titulo = (d.get("titulo") or "").strip()
    if len(titulo) < 3:
        raise EntradaInvalida("Diga qual é o evento ou o projeto.")
    d0, d1 = _data(d.get("data_inicio"), "data de início"), _data(d.get("data_fim") or d.get("data_inicio"), "data de fim")
    if d1 < d0:
        raise EntradaInvalida("A data de fim é anterior à de início.")
    qtd = _num(d.get("quantidade"), "o número de diárias", obrig=True)
    if qtd <= 0:
        raise EntradaInvalida("O número de diárias deve ser maior que zero.")
    if qtd * 2 != int(qtd * 2):
        raise EntradaInvalida("Diárias inteiras ou meia diária (ex.: 1, 1,5, 2).")
    if qtd > (d1 - d0).days + 1:
        raise EntradaInvalida(f"São {(d1 - d0).days + 1} dia(s) no período: no máximo {(d1 - d0).days + 1} diária(s).")
    s.instrutor_id, s.motivo, s.titulo = inst.id, motivo, titulo[:200]
    s.descricao = (d.get("descricao") or "").strip() or None
    s.destino = ((d.get("destino") or "").strip() or None) and d["destino"].strip()[:200]
    s.data_inicio, s.data_fim, s.quantidade = d0, d1, qtd
    s.valor_unitario = _num(d.get("valor_unitario"), "o valor da diária")
    s.outros_recursos = (d.get("outros_recursos") or "").strip() or None
    s.centro_custo = ((d.get("centro_custo") or "").strip() or None) and d["centro_custo"].strip()[:60]


def criar(db: Session, ctx, d: dict) -> SolicitacaoDiaria:
    s = SolicitacaoDiaria(status="solicitada", solicitado_por_id=getattr(ctx, "id", None))
    _preencher(db, s, d)
    if ctx.unidades is not None and db.get(Instrutor, s.instrutor_id).unidade_id not in ctx.unidades:
        raise EntradaInvalida("Instrutor fora das suas unidades.")
    db.add(s)
    db.flush()
    auditoria.registrar(db, ctx, "diaria.solicitar", "solicitacoes_diarias", s.id, depois=auditoria.snapshot(s))
    notificar(db, s.instrutor_id, "diaria", f"Diárias solicitadas: {s.titulo}",
              f"{_fmt(s.quantidade)} diária(s) de {s.data_inicio:%d/%m} a {s.data_fim:%d/%m}" + (f" — {s.destino}" if s.destino else "") + ".", None, ctx)
    return s


def _fmt(q) -> str:
    return f"{float(q):g}".replace(".", ",")


def alterar(db: Session, ctx, sid: int, d: dict) -> SolicitacaoDiaria:
    s = _obter(db, sid)
    if s.status != "solicitada":
        raise ConflitoValidacao("Só dá para alterar a solicitação antes de ela ser aprovada.")
    antes = auditoria.snapshot(s)
    _preencher(db, s, {**serializar(db, s), **d})
    db.flush()
    auditoria.registrar(db, ctx, "diaria.alterar", "solicitacoes_diarias", s.id, antes=antes, depois=auditoria.snapshot(s))
    return s


def _obter(db: Session, sid: int) -> SolicitacaoDiaria:
    s = db.get(SolicitacaoDiaria, sid)
    if s is None:
        raise NaoEncontrado("Solicitação de diárias não encontrada.")
    return s


def decidir(db: Session, ctx, sid: int, status: str, resposta: str | None = None, pago_em=None) -> SolicitacaoDiaria:
    """Aprovar, recusar (com motivo), marcar como paga ou cancelar."""
    s = _obter(db, sid)
    if status not in PROXIMOS.get(s.status, []):
        raise ConflitoValidacao(f"A solicitação está '{STATUS[s.status].lower()}': não dá para passar para '{STATUS.get(status, status).lower()}'.")
    resposta = (resposta or "").strip() or None
    if status in ("recusada", "cancelada") and not resposta:
        raise EntradaInvalida("Diga o motivo (o instrutor recebe o retorno).")
    antes = auditoria.snapshot(s)
    s.status = status
    if status == "paga":
        s.pago_em = _data(pago_em, "data do pagamento") if pago_em else date.today()
    else:
        s.decidido_por_id, s.decidido_em = getattr(ctx, "id", None), datetime.now()
    if resposta:
        s.resposta = resposta
    db.flush()
    auditoria.registrar(db, ctx, f"diaria.{status}", "solicitacoes_diarias", s.id, antes=antes, depois=auditoria.snapshot(s))
    titulo = {"aprovada": f"✅ Diárias aprovadas: {s.titulo}", "paga": f"Diárias pagas: {s.titulo}",
              "recusada": f"Diárias recusadas: {s.titulo}", "cancelada": f"Diárias canceladas: {s.titulo}"}[status]
    notificar(db, s.instrutor_id, "diaria", titulo, resposta or f"{_fmt(s.quantidade)} diária(s) de {s.data_inicio:%d/%m} a {s.data_fim:%d/%m}.", None, ctx)
    return s


def listar(db: Session, status: str | None = None, instrutor_id: int | None = None, unidades=None) -> dict:
    q = select(SolicitacaoDiaria).join(Instrutor, Instrutor.id == SolicitacaoDiaria.instrutor_id)
    if status:
        q = q.where(SolicitacaoDiaria.status == status)
    if instrutor_id:
        q = q.where(SolicitacaoDiaria.instrutor_id == instrutor_id)
    if unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades or [-1]))
    ordem = {"solicitada": 0, "aprovada": 1, "paga": 2, "recusada": 3, "cancelada": 4}
    lista = sorted((serializar(db, s) for s in db.scalars(q.order_by(SolicitacaoDiaria.data_inicio.desc()).limit(500))),
                   key=lambda x: (ordem.get(x["status"], 9), x["data_inicio"]))
    tot = {k: {"qtd": 0, "diarias": 0.0, "valor": 0.0} for k in STATUS}
    for x in lista:
        t = tot[x["status"]]
        t["qtd"] += 1
        t["diarias"] += x["quantidade"]
        t["valor"] += x["valor_total"] or 0
    return {"itens": lista, "totais": {k: {**v, "rotulo": STATUS[k], "valor": round(v["valor"], 2)} for k, v in tot.items()},
            "motivos": [{"valor": k, "rotulo": v} for k, v in MOTIVOS.items()]}
