"""Termo de horas do instrutor horista.

- Mensalista: jornada semanal fixa (ex.: 40 h), com o teto de 90% para aulas.
- Horista: recebe todo mês um TERMO DE HORAS, que define as horas de aula que ele assume naquele mês (e outras
  ocupações) e, se for o caso, os dias da semana. O termo muda de um mês para outro e é ADAPTÁVEL: numa urgência
  (alguém num dia ou num total de horas fora do termo) ele é ajustado, desde que o instrutor concorde — o ajuste fica
  registrado com o motivo. Por isso aula fora do termo é alerta, não bloqueio; o que impede de fato é o instrutor já
  estar ocupado e a carga máxima do contrato (limite semanal do cadastro), como no mensalista.
- Simulação e previsão de turmas não olham o termo: contam só a ocupação real e a carga máxima do contrato.
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


def termo_dict(t: TermoHoras, programadas: float | None = None) -> dict:
    d = {"id": t.id, "mes": t.mes.isoformat()[:7], "rotulo": rotulo_mes(t.mes), "horas_aula": float(t.horas_aula),
         "horas_outras": float(t.horas_outras or 0), "observacao": t.observacao, "dias_semana": sorted(t.dias_semana) if t.dias_semana else [],
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


def _dias(dias) -> list[int] | None:
    if dias is None:
        return None
    try:
        ds = sorted({int(x) for x in dias})
    except (TypeError, ValueError):
        raise EntradaInvalida("Dias do termo inválidos.")
    if any(x < 0 or x > 5 for x in ds):
        raise EntradaInvalida("Os dias do termo vão de segunda (0) a sábado (5).")
    return ds or None


def salvar(db: Session, ctx, inst: Instrutor, mes, horas_aula, horas_outras=0, observacao: str | None = None,
           cenario_id: int | None = None, dias_semana=None) -> dict:
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
    t.dias_semana = _dias(dias_semana)
    db.flush()
    auditoria.registrar(db, ctx, "termo_horas.salvar", "termos_horas", t.id, antes=antes, depois=auditoria.snapshot(t))
    notificar(db, inst.id, "cadastro", f"Termo de horas de {rotulo_mes(m)}", f"{ha:g} h de aula" + (f" e {ho:g} h de outras atividades" if ho else "") + " no mês.",
              "turmas", ctx)
    prog = horas_programadas(db, cenario_id, inst.id, m) if cenario_id else None
    res = termo_dict(t, prog)
    if prog is not None and prog > ha + 1e-6:
        num = lambda v: f"{v:g}".replace(".", ",")  # noqa: E731
        res["aviso"] = (f"Já há {num(prog)} h de aula programadas em {rotulo_mes(m)}, {num(prog - ha)} h acima do novo termo: "
                        "ajuste o termo por urgência (com a concordância do instrutor) ou passe as aulas excedentes para outro instrutor.")
    return res


DIAS_NOME = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado"]


def ajustar(db: Session, ctx, inst: Instrutor, mes, motivo: str, concordancia: bool, horas_aula=None, incluir_dias=None,
            cenario_id: int | None = None) -> dict:
    """Ajuste do termo por urgência (mais horas no mês e/ou um dia fora do termo). Só com a concordância do instrutor,
    registrada com o motivo na auditoria, na observação do termo e no aviso ao instrutor."""
    from app.services.notificacoes import notificar
    if inst.modalidade != "horista":
        raise EntradaInvalida(f"{inst.nome} é mensalista: não tem termo de horas.")
    if not concordancia:
        raise EntradaInvalida("O ajuste do termo precisa da concordância do instrutor: confirme que ele concordou.")
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise EntradaInvalida("Descreva o motivo do ajuste (a urgência).")
    m = _mes_param(mes)
    t = db.scalar(select(TermoHoras).where(TermoHoras.instrutor_id == inst.id, TermoHoras.mes == m))
    antes = auditoria.snapshot(t) if t else None
    if t is None:
        t = TermoHoras(instrutor_id=inst.id, mes=m, horas_aula=0, horas_outras=0)
        db.add(t)
    mudou = []
    if horas_aula not in (None, ""):
        try:
            ha = float(horas_aula)
        except (TypeError, ValueError):
            raise EntradaInvalida("Horas do termo inválidas.")
        if ha < 0 or ha + float(t.horas_outras or 0) > 220:
            raise EntradaInvalida("As horas do termo vão de 0 a 220 no mês.")
        mudou.append(f"{float(t.horas_aula or 0):g} → {ha:g} h de aula".replace(".", ","))
        t.horas_aula = ha
    novos = _dias(incluir_dias) or []
    if novos and t.dias_semana:
        extra = [d for d in novos if d not in t.dias_semana]
        if extra:
            t.dias_semana = sorted(set(t.dias_semana) | set(extra))
            mudou.append("inclui " + ", ".join(DIAS_NOME[d] for d in extra))
    if not mudou:
        raise EntradaInvalida("Nada a ajustar: informe as novas horas do mês ou o dia a incluir.")
    nota = f"Ajuste em {date.today():%d/%m} ({'; '.join(mudou)}): {motivo} — instrutor de acordo."
    t.observacao = f"{t.observacao}\n{nota}" if t.observacao else nota
    t.atualizado_por_id = getattr(ctx, "id", None)
    db.flush()
    auditoria.registrar(db, ctx, "termo_horas.ajuste_urgencia", "termos_horas", t.id, antes=antes,
                        depois={**auditoria.snapshot(t), "motivo": motivo, "concordancia_instrutor": True}, motivo=motivo)
    notificar(db, inst.id, "cadastro", f"Termo de {rotulo_mes(m)} ajustado (com a sua concordância)", f"{'; '.join(mudou)}. Motivo: {motivo}", "turmas", ctx)
    prog = horas_programadas(db, cenario_id, inst.id, m) if cenario_id else None
    return {**termo_dict(t, prog), "ajuste": nota}


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
            base = {"instrutor": i.nome, "mes": rotulo_mes(m), "_instrutor_id": i.id, "_mes": m.isoformat()[:7]}
            if t is None and prog > 0:
                res.append({**base, "problema": "sem termo de horas do mês", "programadas_h": prog, "termo_h": None})
                continue
            if t is None:
                continue
            if prog > float(t.horas_aula) + 1e-6:
                res.append({**base, "problema": f"{prog - float(t.horas_aula):g} h acima do termo".replace(".", ","),
                            "programadas_h": prog, "termo_h": float(t.horas_aula)})
            if t.dias_semana:
                fora = sorted({d.weekday() for d in db.scalars(select(Alocacao.data).where(
                    Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == i.id, Alocacao.status != "cancelada",
                    Alocacao.data >= max(m, hoje), Alocacao.data <= fim_do_mes(m))) if d.weekday() not in t.dias_semana})
                if fora:
                    res.append({**base, "problema": "aula em dia fora do termo (" + ", ".join(DIAS_NOME[d] for d in fora if d < 6) + ")",
                                "programadas_h": prog, "termo_h": float(t.horas_aula), "_dias_fora": fora})
    return res
