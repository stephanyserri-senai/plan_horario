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


# termo por dia e turno (grade do mês): M = matutino, V = vespertino, N = noturno, S = sábado; cada célula é aula ou PL
TURNOS_TERMO = ("M", "V", "N", "S")
NOME_TURNO = {"M": "matutino", "V": "vespertino", "N": "noturno", "S": "sábado"}
HORAS_TURNO = {"M": 220 / 60, "V": 220 / 60, "N": 200 / 60, "S": 220 / 60}  # sem horário: 4 aulas de 55 min (de dia) ou 50 min (à noite)
HORAS_PL = 4.0  # turno de planejamento/projeto sem horário
# o termo é o tempo PAGO para o instrutor estar disponível: aula, planejamento (PL), projeto (PJ) ou ajuste de urgência
TIPOS_TERMO = {"aula": "Aula", "pl": "Planejamento (PL)", "pj": "Projeto (PJ)", "urgencia": "Ajuste de urgência"}
DE_AULA = ("aula", "urgencia")  # turnos em que ele pode estar em sala (urgência = pago para cobrir aula fora do previsto)
# horários de entrada e saída usuais de cada turno (dependem do turno de entrada do instrutor e do curso); outro horário também vale
HORARIOS_TURNO = {"M": [("07:30", "11:30"), ("08:00", "12:00")], "V": [("13:30", "17:30"), ("13:00", "17:30"), ("13:00", "17:00")],
                  "N": [("18:30", "22:00"), ("18:00", "22:00")], "S": [("09:00", "13:00"), ("08:00", "12:00")]}
FAIXA_TURNO = {"M": ("06:00", "13:00"), "V": ("12:00", "18:30"), "N": ("17:30", "23:00"), "S": ("06:00", "18:30")}


def tipo_cel(v) -> str | None:
    """Célula da grade: "aula" | "pl" (antigo) ou {"tipo": "aula"|"pl", "ini": "HH:MM", "fim": "HH:MM"}."""
    return v.get("tipo") if isinstance(v, dict) else v


def janela_cel(v) -> tuple[str, str] | None:
    return (v["ini"], v["fim"]) if isinstance(v, dict) and v.get("ini") and v.get("fim") else None


def _min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def horas_cel(tn: str, v) -> float:
    """Horas que o turno conta no termo: pelo horário de entrada e saída do dia (ex.: 13:00–17:30 = 4,5 h); sem horário, o padrão."""
    j = janela_cel(v)
    if j:
        return (_min(j[1]) - _min(j[0])) / 60
    return HORAS_TURNO[tn] if tipo_cel(v) in DE_AULA else HORAS_PL


def turno_da_aula(inicio) -> str:
    if inicio.weekday() == 5:
        return "S"
    return "M" if inicio.hour < 12 else "V" if inicio.hour < 18 else "N"


def cobre(t: TermoHoras, inicio, fim=None) -> bool:
    """A aula cai num turno com aula no termo, dentro do horário daquele dia? (termo sem agenda: vale o dia da semana)."""
    if t.agenda:
        v = (t.agenda.get(inicio.date().isoformat()) or {}).get(turno_da_aula(inicio))
        if tipo_cel(v) not in DE_AULA:
            return False
        j = janela_cel(v)
        if j and fim is not None:
            return _min(j[0]) <= inicio.hour * 60 + inicio.minute and fim.hour * 60 + fim.minute <= _min(j[1])
        return True
    return not t.dias_semana or inicio.weekday() in t.dias_semana


def resumo_agenda(agenda: dict | None) -> dict:
    cel = [(d, tn, v) for d, ts in (agenda or {}).items() for tn, v in ts.items()]
    por = {k: [c for c in cel if tipo_cel(c[2]) == k] for k in TIPOS_TERMO}
    horas = {k: round(sum(horas_cel(c[1], c[2]) for c in v), 1) for k, v in por.items()}
    aula = por["aula"] + por["urgencia"]
    return {"turnos_aula": len(aula), "turnos_pl": len(por["pl"]) + len(por["pj"]),
            "horas_aula": round(horas["aula"] + horas["urgencia"], 1), "horas_pl": round(horas["pl"] + horas["pj"], 1),
            "por_tipo": {k: {"turnos": len(por[k]), "horas": horas[k], "rotulo": TIPOS_TERMO[k]} for k in TIPOS_TERMO},
            "total_pago_h": round(sum(horas.values()), 1), "dias": len({c[0] for c in cel})}


def _agenda(agenda, m: date) -> dict | None:
    """Valida a grade do mês: só datas do mês, turnos M/V/N na semana e S no sábado, valores aula ou pl."""
    if agenda is None:
        return None
    if not isinstance(agenda, dict):
        raise EntradaInvalida("Grade do termo inválida.")
    res = {}
    for k, ts in agenda.items():
        try:
            d = date.fromisoformat(str(k)[:10])
        except ValueError:
            raise EntradaInvalida(f"Data inválida na grade do termo: {k}.")
        if mes_de(d) != m:
            raise EntradaInvalida(f"{d:%d/%m/%Y} não é de {rotulo_mes(m)}.")
        if d.weekday() == 6:
            raise EntradaInvalida("Domingo não entra no termo.")
        validos = ("S",) if d.weekday() == 5 else ("M", "V", "N")
        cel = {}
        for tn, v in (ts or {}).items():
            tipo = tipo_cel(v)
            if tipo in (None, "", "livre"):
                continue
            if tn not in validos or tipo not in TIPOS_TERMO:
                raise EntradaInvalida(f"Turno {tn}={tipo} inválido em {d:%d/%m} (use {', '.join(validos)} com aula, pl, pj ou urgencia).")
            j = janela_cel(v)
            if j:
                try:
                    a0, a1 = _min(j[0]), _min(j[1])
                except (ValueError, AttributeError):
                    raise EntradaInvalida(f"Horário inválido em {d:%d/%m}: use HH:MM.")
                f0, f1 = (_min(x) for x in FAIXA_TURNO[tn])
                if not (f0 <= a0 < a1 <= f1):
                    raise EntradaInvalida(f"Horário {j[0]}–{j[1]} em {d:%d/%m} não cabe no turno {NOME_TURNO[tn]} ({FAIXA_TURNO[tn][0]}–{FAIXA_TURNO[tn][1]}).")
                cel[tn] = {"tipo": tipo, "ini": j[0], "fim": j[1]}
            else:
                cel[tn] = {"tipo": tipo}
        if cel:
            res[d.isoformat()] = cel
    return res


def horas_por_semana(agenda: dict | None) -> dict[str, float]:
    """Horas pagas da grade por semana (segunda da semana → horas)."""
    res: dict[str, float] = {}
    for d, ts in (agenda or {}).items():
        dd = date.fromisoformat(d)
        k = (dd - timedelta(days=dd.weekday())).isoformat()
        res[k] = res.get(k, 0.0) + sum(horas_cel(tn, v) for tn, v in ts.items())
    return res


def _limite_semanal(agenda: dict):
    from app.services.regras_aula import MAX_HORAS_SEMANA
    for seg, horas in sorted(horas_por_semana(agenda).items()):
        if horas > MAX_HORAS_SEMANA + 1e-6:
            raise EntradaInvalida(f"Semana de {date.fromisoformat(seg):%d/%m}: {f'{horas:.1f}'.replace('.', ',')} h no termo. Ninguém trabalha "
                                  f"mais de {MAX_HORAS_SEMANA:g} h por semana (aula, planejamento, projeto e urgência somados).")


def termo_dict(t: TermoHoras, programadas: float | None = None) -> dict:
    d = {"id": t.id, "mes": t.mes.isoformat()[:7], "rotulo": rotulo_mes(t.mes), "horas_aula": float(t.horas_aula),
         "horas_outras": float(t.horas_outras or 0), "observacao": t.observacao, "dias_semana": sorted(t.dias_semana) if t.dias_semana else [],
         "atualizado_em": t.atualizado_em.isoformat() if t.atualizado_em else None, "agenda": t.agenda or {},
         "resumo_agenda": resumo_agenda(t.agenda)}
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


def dias_com_aula(db: Session, cenario_id: int | None, instrutor_id: int, mes: date) -> list[int]:
    """Dias da semana em que o instrutor tem aula programada no mês."""
    if not cenario_id:
        return []
    return sorted({d.weekday() for d in db.scalars(select(Alocacao.data).where(
        Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == instrutor_id, Alocacao.status != "cancelada",
        Alocacao.data >= mes, Alocacao.data <= fim_do_mes(mes)))})


def proximo_mes(m: date) -> date:
    return date(m.year + m.month // 12, m.month % 12 + 1, 1)


def painel(db: Session, inst: Instrutor, cenario_id: int | None, hoje: date | None = None, ate: date | None = None,
           desde: date | None = None) -> dict:
    """Termo de horas do horista para consulta e edição: os meses (do mês passado ao fim do semestre ou ao próximo mês), com
    as horas programadas e os dias com aula fora do termo; e o termo do PRÓXIMO mês, feito no fim de cada mês, com a sugestão
    do que precisa entrar nele — inclusive os dias em que foi preciso contar com o instrutor fora do termo deste mês
    (o que não estava previsto no termo vai para o termo do mês seguinte)."""
    hoje = hoje or date.today()
    atual = mes_de(hoje)
    prox = proximo_mes(atual)
    d0 = date(atual.year - (1 if atual.month == 1 else 0), 12 if atual.month == 1 else atual.month - 1, 1)
    if desde:  # o semestre inteiro, quando há um
        d0 = min(d0, mes_de(desde))
    d1 = fim_do_mes(max(prox, mes_de(ate) if ate else prox))
    meses = listar(db, inst, cenario_id, d0, d1)
    termos_ = termos_do(db, [inst.id], d0, d1).get(inst.id, {})
    for m in meses:
        md = _mes_param(m["mes"])
        m["situacao"] = "passado" if md < atual else "atual" if md == atual else "proximo" if md == prox else "futuro"
        pares = [] if not cenario_id else list(db.execute(select(Alocacao.inicio, Alocacao.fim).where(
            Alocacao.cenario_id == cenario_id, Alocacao.instrutor_id == inst.id, Alocacao.status != "cancelada",
            Alocacao.data >= md, Alocacao.data <= fim_do_mes(md))))
        inicios = [p_[0] for p_ in pares]
        por_data: dict[str, set] = {}
        for i in inicios:
            por_data.setdefault(i.date().isoformat(), set()).add(turno_da_aula(i))
        m["aulas_por_data"] = {k: sorted(v, key=TURNOS_TERMO.index) for k, v in sorted(por_data.items())}
        hor: dict[str, dict[str, list]] = {}  # horário das aulas lançadas em cada dia e turno (para conferir com o horário do termo)
        for i, f_ in pares:
            x = hor.setdefault(i.date().isoformat(), {}).setdefault(turno_da_aula(i), [f"{i:%H:%M}", f"{f_:%H:%M}"])
            x[0], x[1] = min(x[0], f"{i:%H:%M}"), max(x[1], f"{f_:%H:%M}")
        m["horarios_aulas"] = hor
        dias = sorted({i.weekday() for i in inicios})
        m["dias_com_aula"] = dias
        t = termos_.get(md)
        fora = sorted({(i.date().isoformat(), turno_da_aula(i)) for i, f_ in pares if t is not None and not cobre(t, i, f_)})
        m["fora"] = [{"data": d, "turno": tn} for d, tn in fora]
        m["dias_fora"] = sorted({date.fromisoformat(d).weekday() for d, _ in fora})
    por_mes = {m["mes"]: m for m in meses}
    ma, mp = por_mes.get(atual.isoformat()[:7], {}), por_mes.get(prox.isoformat()[:7], {})
    motivos, dias_sug = [], set(ma.get("dias_semana") or [])
    # dias só importam quando o termo restringe os dias (termo sem dias = qualquer dia)
    if dias_sug or mp.get("dias_semana"):
        for d in [x for x in ma.get("dias_fora") or [] if x < 6]:
            motivos.append(f"{DIAS_NOME[d]}: houve aula fora do termo em {rotulo_mes(atual)} — entra no termo de {rotulo_mes(prox)}")
            dias_sug.add(d)
        base_prox = set(mp.get("dias_semana") or []) if mp.get("tem_termo") else dias_sug
        for d in [x for x in mp.get("dias_com_aula") or [] if x < 6]:
            if d not in base_prox and d not in dias_sug:
                motivos.append(f"{DIAS_NOME[d]}: já há aula programada em {rotulo_mes(prox)}")
            dias_sug.add(d)
    padrao: dict[int, dict[str, str]] = {}
    for d, ts in (ma.get("agenda") or {}).items():
        for tn, v in ts.items():
            atual_v = padrao.get(date.fromisoformat(d).weekday(), {}).get(tn)
            if tipo_cel(atual_v) not in DE_AULA:  # aula prevalece; o horário do dia vai junto
                novo = dict(v) if isinstance(v, dict) else {"tipo": v}
                if novo["tipo"] == "urgencia":  # o que foi urgência neste mês entra como aula prevista no próximo termo
                    novo["tipo"] = "aula"
                padrao.setdefault(date.fromisoformat(d).weekday(), {})[tn] = novo
    for f in ma.get("fora") or []:
        padrao.setdefault(date.fromisoformat(f["data"]).weekday(), {}).setdefault(f["turno"], {"tipo": "aula"})
        if tipo_cel(padrao[date.fromisoformat(f["data"]).weekday()][f["turno"]]) != "aula":
            padrao[date.fromisoformat(f["data"]).weekday()][f["turno"]] = {"tipo": "aula"}
    for d, ts in (mp.get("aulas_por_data") or {}).items():
        for tn in ts:
            if tipo_cel(padrao.get(date.fromisoformat(d).weekday(), {}).get(tn)) != "aula":
                padrao.setdefault(date.fromisoformat(d).weekday(), {})[tn] = {"tipo": "aula"}
    agenda_sug = {}
    if ma.get("agenda") or padrao:
        dd = prox
        while dd <= fim_do_mes(prox):
            if dd.weekday() in padrao and dd.weekday() < 6:
                agenda_sug[dd.isoformat()] = {tn: v for tn, v in padrao[dd.weekday()].items() if (tn == "S") == (dd.weekday() == 5)}
            dd += timedelta(days=1)
        agenda_sug = {k: v for k, v in agenda_sug.items() if v}
    horas_sug = max(float(mp.get("programadas_h") or 0), float(ma.get("horas_aula") or 0) if ma.get("tem_termo") else 0.0)
    proximo = {"mes": prox.isoformat()[:7], "rotulo": rotulo_mes(prox), "prazo": fim_do_mes(atual).isoformat(), "tem_termo": bool(mp.get("tem_termo")),
               "faltam_dias": (fim_do_mes(atual) - hoje).days, "programadas_h": mp.get("programadas_h"),
               "horas_aula": mp.get("horas_aula"), "excedente_h": mp.get("excedente_h") or 0,
               "sugestao": {"horas_aula": round(max(horas_sug, resumo_agenda(agenda_sug)["horas_aula"]), 1), "dias_semana": sorted(d for d in dias_sug if d < 6),
                            "agenda": agenda_sug, "horas_outras": resumo_agenda(agenda_sug)["horas_pl"], "motivos": motivos},
               "pendente": [x for x in motivos if "fora do termo" in x and mp.get("tem_termo") and mp.get("dias_semana")
                            and DIAS_NOME.index(x.split(":")[0]) not in mp["dias_semana"]]}
    return {"instrutor": {"id": inst.id, "nome": inst.nome, "modalidade": inst.modalidade, "carga_semanal": float(inst.carga_horaria_contratual or 0)},
            "hoje": hoje.isoformat(), "mes_atual": atual.isoformat()[:7], "proximo": proximo, "meses": meses}


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
           cenario_id: int | None = None, dias_semana=None, agenda=None) -> dict:
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
    grade = _agenda(agenda, m)
    if grade is not None:
        _limite_semanal(grade)
        t.agenda = grade or None
    if t.agenda:  # com a grade, os dias da semana do termo saem dela (dias com aula)
        t.dias_semana = sorted({date.fromisoformat(d).weekday() for d, ts in t.agenda.items() if any(tipo_cel(v) in DE_AULA for v in ts.values())}) or None
    else:
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
            cenario_id: int | None = None, incluir_turnos=None) -> dict:
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
    if incluir_turnos and t.agenda:  # termo por dia e turno: inclui as células (data, turno) com aula
        ag = {k: dict(v) for k, v in t.agenda.items()}
        novas = []
        for x in incluir_turnos:
            dd = date.fromisoformat(str(x["data"])[:10])
            tn = x.get("turno") or "M"
            if mes_de(dd) == m and tipo_cel(ag.get(dd.isoformat(), {}).get(tn)) not in DE_AULA:
                cel = {"tipo": "urgencia"}  # o turno incluído por urgência fica marcado como tal (é pago como ajuste de urgência)
                if x.get("ini") and x.get("fim"):
                    cel.update(ini=x["ini"], fim=x["fim"])
                ag.setdefault(dd.isoformat(), {})[tn] = cel
                novas.append(f"{dd:%d/%m} {NOME_TURNO.get(tn, tn)}")
        if novas:
            _limite_semanal(ag)
            t.agenda = ag
            t.dias_semana = sorted({date.fromisoformat(d).weekday() for d, ts in ag.items() if any(tipo_cel(v) in DE_AULA for v in ts.values())}) or None
            mudou.append("inclui " + ", ".join(novas))
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
