"""Termo de horas do instrutor horista e a capacidade de cada modalidade.

- Mensalista: jornada semanal fixa (ex.: 40 h), com o teto de 90% para aulas; a ocupação é medida sobre ela.
- Horista: recebe todo mês um TERMO DE HORAS, que define quantas horas de aula ele assume naquele mês (e outras
  ocupações). O termo muda de um mês para outro. Com termo, as aulas do mês não passam das horas do termo
  (validação central) e a ocupação é medida sobre o termo; sem termo do mês, vale o limite semanal do cadastro
  e o caso aparece em Riscos para a coordenação registrar o termo.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import EntradaInvalida
from app.models import Alocacao, Instrutor, TermoHoras
from app.services import auditoria

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def mes_de(d: date) -> date:
    return date(d.year, d.month, 1)


def fim_do_mes(m: date) -> date:
    return date(m.year, m.month, calendar.monthrange(m.year, m.month)[1])


def rotulo_mes(m: date) -> str:
    return f"{MESES[m.month - 1]}/{m.year}"


def meses_entre(d0: date, d1: date) -> list[date]:
    res, m = [], mes_de(d0)
    while m <= d1:
        res.append(m)
        m = fim_do_mes(m) + timedelta(days=1)
    return res


def termos_do(db: Session, instrutor_ids, d0: date, d1: date) -> dict[int, dict[date, TermoHoras]]:
    """Termos dos instrutores nos meses do intervalo: {instrutor: {mês: termo}}."""
    ids = list(instrutor_ids)
    res: dict[int, dict[date, TermoHoras]] = defaultdict(dict)
    if not ids:
        return res
    for t in db.scalars(select(TermoHoras).where(TermoHoras.instrutor_id.in_(ids), TermoHoras.mes >= mes_de(d0), TermoHoras.mes <= d1)):
        res[t.instrutor_id][t.mes] = t
    return res


def horas_programadas(db: Session, cenario_id: int, instrutor_id: int, mes: date) -> float:
    m = db.scalar(select(func.coalesce(func.sum(Alocacao.minutos_aula), 0)).where(
        Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == instrutor_id, Alocacao.status != "cancelada",
        Alocacao.data >= mes, Alocacao.data <= fim_do_mes(mes)))
    return round(float(m or 0) / 60, 1)


def capacidade_semanal(inst: Instrutor, d0: date, d1: date, termos: dict[date, TermoHoras] | None) -> tuple[float, bool]:
    """Horas por semana sobre as quais se mede a ocupação, e se vieram do termo.
    Horista com termo em todos os meses do período: as horas de aula dos termos proporcionais aos dias do período.
    Senão (mensalista, ou horista sem termo), a carga semanal do cadastro."""
    carga = float(inst.carga_horaria_contratual or 0)
    if inst.modalidade != "horista" or not termos:
        return carga, False
    meses = meses_entre(d0, d1)
    if any(m not in termos for m in meses):
        return carga, False
    total = 0.0
    for m in meses:
        ini, fim = max(m, d0), min(fim_do_mes(m), d1)
        total += float(termos[m].horas_aula) * ((fim - ini).days + 1) / ((fim_do_mes(m) - m).days + 1)
    semanas = max(1.0, ((d1 - d0).days + 1) / 7)
    return total / semanas, True


def termo_dict(t: TermoHoras, programadas: float | None = None) -> dict:
    d = {"id": t.id, "mes": t.mes.isoformat()[:7], "rotulo": rotulo_mes(t.mes), "horas_aula": float(t.horas_aula),
         "horas_outras": float(t.horas_outras or 0), "observacao": t.observacao,
         "atualizado_em": t.atualizado_em.isoformat() if t.atualizado_em else None}
    if programadas is not None:
        d["programadas_h"] = programadas
        d["pct"] = round(100 * programadas / float(t.horas_aula), 1) if float(t.horas_aula) else (0.0 if not programadas else 999.0)
        d["excedente_h"] = round(max(0.0, programadas - float(t.horas_aula)), 1)
        d["livre_h"] = round(max(0.0, float(t.horas_aula) - programadas), 1)
    return d


def listar(db: Session, inst: Instrutor, cenario_id: int | None, d0: date, d1: date) -> list[dict]:
    """Um item por mês do período: o termo (ou a falta dele) e as horas já programadas no semestre."""
    termos = termos_do(db, [inst.id], d0, d1).get(inst.id, {})
    res = []
    for m in meses_entre(d0, d1):
        prog = horas_programadas(db, cenario_id, inst.id, m) if cenario_id else None
        if m in termos:
            res.append({**termo_dict(termos[m], prog), "tem_termo": True})
        else:
            res.append({"mes": m.isoformat()[:7], "rotulo": rotulo_mes(m), "tem_termo": False, "programadas_h": prog})
    return res


def _mes_param(mes: str | date) -> date:
    if isinstance(mes, date):
        return mes_de(mes)
    try:
        a, m = str(mes)[:7].split("-")
        return date(int(a), int(m), 1)
    except (ValueError, TypeError):
        raise EntradaInvalida("Informe o mês do termo no formato AAAA-MM.")


def salvar(db: Session, ctx, inst: Instrutor, mes, horas_aula, horas_outras=0, observacao: str | None = None,
           cenario_id: int | None = None) -> dict:
    """Registra ou altera o termo do mês (o termo pode mudar; cada mudança fica na auditoria e o instrutor é avisado)."""
    from app.services.notificacoes import notificar
    if inst.modalidade != "horista":
        raise EntradaInvalida(f"{inst.nome} é mensalista: a jornada é semanal e fixa ({float(inst.carga_horaria_contratual):g} h); termo de horas é só do horista.")
    m = _mes_param(mes)
    try:
        ha, ho = float(horas_aula), float(horas_outras or 0)
    except (TypeError, ValueError):
        raise EntradaInvalida("Horas do termo inválidas.")
    if ha < 0 or ho < 0 or ha + ho > 220:
        raise EntradaInvalida("As horas do termo vão de 0 a 220 no mês.")
    t = db.scalar(select(TermoHoras).where(TermoHoras.instrutor_id == inst.id, TermoHoras.mes == m))
    antes = auditoria.snapshot(t) if t else None
    if t is None:
        t = TermoHoras(instrutor_id=inst.id, mes=m)
        db.add(t)
    t.horas_aula, t.horas_outras, t.observacao, t.atualizado_por_id = ha, ho, (observacao or None), getattr(ctx, "id", None)
    db.flush()
    auditoria.registrar(db, ctx, "termo_horas.salvar", "termos_horas", t.id, antes=antes, depois=auditoria.snapshot(t))
    notificar(db, inst.id, "cadastro", f"Termo de horas de {rotulo_mes(m)}", f"{ha:g} h de aula" + (f" e {ho:g} h de outras atividades" if ho else "") + " no mês.",
              "turmas", ctx)
    prog = horas_programadas(db, cenario_id, inst.id, m) if cenario_id else None
    res = termo_dict(t, prog)
    if prog is not None and prog > ha + 1e-6:
        num = lambda v: f"{v:g}".replace(".", ",")  # noqa: E731
        res["aviso"] = (f"Já há {num(prog)} h de aula programadas em {rotulo_mes(m)}, {num(prog - ha)} h acima do novo termo: "
                        "passe as aulas excedentes para outro instrutor (substituição) — o caso aparece em Riscos.")
    return res


def pendencias(db: Session, cenario_id: int, unidades, hoje: date, fim: date) -> list[dict]:
    """Horistas com aula programada num mês sem termo, ou com mais horas de aula do que o termo do mês."""
    q = select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.modalidade == "horista")
    if unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades))
    insts = db.scalars(q.order_by(Instrutor.nome)).all()
    termos = termos_do(db, [i.id for i in insts], hoje, fim)
    res = []
    for i in insts:
        for m in meses_entre(hoje, fim):
            prog = horas_programadas(db, cenario_id, i.id, m)
            t = termos.get(i.id, {}).get(m)
            if t is None and prog > 0:
                res.append({"instrutor": i.nome, "mes": rotulo_mes(m), "problema": "sem termo de horas do mês", "programadas_h": prog, "termo_h": None})
            elif t is not None and prog > float(t.horas_aula) + 1e-6:
                res.append({"instrutor": i.nome, "mes": rotulo_mes(m), "problema": f"{prog - float(t.horas_aula):g} h acima do termo".replace(".", ","),
                            "programadas_h": prog, "termo_h": float(t.horas_aula)})
    return res
