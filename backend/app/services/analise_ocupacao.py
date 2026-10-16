"""Consultas de situação, rankings, ocupação no tempo e análise do quadro de instrutores.

Ocupação da jornada (instrutor) = horas de aula na semana ÷ carga contratual semanal.
Referências da instituição: ideal até 80%, teto de 90% (40 h → 9 de 10 turnos; 20 h → 4 de 5).
Quadro de instrutores: contratar vem da ocupação; a proporção de 5 instrutores para 4 turmas (1,25 por turma)
é um aviso, que pesa quando a folga dos instrutores não comporta mais uma turma.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Alocacao, Ambiente, Area, Bloqueio, CenarioPlanejamento, DisponibilidadeInstrutor, Instrutor, Turma, TurmaUC, Turno,
                        UnidadeCurricular)
from app.services.regras_aula import HORAS_POR_TURNO, OCUPACAO_MAXIMA

OCUPACAO_IDEAL = 0.80
INSTRUTORES_POR_TURMA = 5 / 4  # 5 instrutores para 4 turmas
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def faixa(pct: float) -> str:
    """Faixa de ocupação da jornada: ociosa (<50), baixa (<70), ideal (70–80), atenção (80–90), acima do teto (>90)."""
    if pct > OCUPACAO_MAXIMA * 100 + 1e-6:
        return "acima_teto"
    if pct > OCUPACAO_IDEAL * 100 + 1e-6:
        return "atencao"
    if pct >= 70:
        return "ideal"
    if pct >= 50:
        return "baixa"
    return "ociosa"


def _seg(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _instrutores(db, unidades):
    q = select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.situacao == "ativo")
    if unidades is not None:
        q = q.where(Instrutor.unidade_id.in_(unidades))
    return db.scalars(q.order_by(Instrutor.nome)).all()


def _ambientes(db, unidades):
    q = select(Ambiente).where(Ambiente.ativo.is_(True))
    if unidades is not None:
        q = q.where(Ambiente.unidade_id.in_(unidades))
    return db.scalars(q.order_by(Ambiente.codigo)).all()


def _turnos(db, unidades):
    q = select(Turno).where(Turno.ativo.is_(True))
    if unidades is not None:
        q = q.where(Turno.unidade_id.in_(unidades))
    return db.scalars(q.order_by(Turno.hora_inicio)).all()


def _turno_de(turnos, unidade_id, h):
    return next((t for t in turnos if t.unidade_id == unidade_id and t.hora_inicio <= h < t.hora_fim), None)


# ----------------------------------------------------------------------------- situação num dia
def situacao_no_dia(db: Session, cenario_id: int, dia: date, turno_codigo: str | None = None, unidades=None) -> dict:
    """Quem está onde: cada instrutor e cada sala em cada turno do dia (aula, PL/PJ, bloqueio, livre, fora da jornada)."""
    from app.services.calendario import Calendarios
    turnos = [t for t in _turnos(db, unidades) if not turno_codigo or t.codigo == turno_codigo]
    insts, ambs = _instrutores(db, unidades), _ambientes(db, unidades)
    aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.data == dia, Alocacao.status != "cancelada")).all()
    turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.id.in_({a.turma_id for a in aulas})))} if aulas else {}
    ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({a.uc_id for a in aulas})))} if aulas else {}
    nome_inst = {i.id: i.nome for i in db.scalars(select(Instrutor))}
    cod_amb = {a.id: a.codigo for a in db.scalars(select(Ambiente))}
    d0, d1 = datetime.combine(dia, datetime.min.time()), datetime.combine(dia + timedelta(days=1), datetime.min.time())
    bloqs = db.scalars(select(Bloqueio).where(Bloqueio.ativo.is_(True), Bloqueio.inicio < d1, Bloqueio.fim > d0,
                                              Bloqueio.alvo_tipo.in_(["instrutor", "ambiente"]))).all()
    disp = defaultdict(list)
    for x in db.scalars(select(DisponibilidadeInstrutor).where(DisponibilidadeInstrutor.dia_semana == dia.weekday())):
        disp[x.instrutor_id].append(x)
    cal = Calendarios(db)
    unidades_dia = {t.unidade_id for t in turnos}
    letivo = {u: cal.dia_letivo_unidade(u, dia) for u in unidades_dia}

    def janela(t):
        return datetime.combine(dia, t.hora_inicio), datetime.combine(dia, t.hora_fim)

    def desc_aula(a):
        t, u = turmas.get(a.turma_id), ucs.get(a.uc_id)
        return {"turma": t.codigo if t else "?", "uc": f"{u.codigo} – {u.nome}" if u else "?", "instrutor": nome_inst.get(a.instrutor_id),
                "sala": cod_amb.get(a.ambiente_id), "horario": f"{a.inicio:%H:%M}–{a.fim:%H:%M}"}

    linhas_i = []
    for i in insts:
        cel = {}
        for t in [t for t in turnos if t.unidade_id == i.unidade_id]:
            ini, fim = janela(t)
            da = [a for a in aulas if a.instrutor_id == i.id and a.inicio < fim and a.fim > ini]
            bs = [b for b in bloqs if b.alvo_tipo == "instrutor" and b.alvo_id == i.id and b.inicio < fim and b.fim > ini]
            na_jornada = any(x.hora_inicio <= t.hora_inicio and x.hora_fim >= t.hora_fim for x in disp[i.id])
            if da:
                cel[t.codigo] = {"estado": "aula", **desc_aula(da[0])}
            elif any(b.tipo in ("planejamento", "projeto", "treinamento") for b in bs):
                b = next(b for b in bs if b.tipo in ("planejamento", "projeto", "treinamento"))
                cel[t.codigo] = {"estado": {"planejamento": "PL", "projeto": "PJ", "treinamento": "TR"}[b.tipo], "detalhe": b.motivo}
            elif bs:
                cel[t.codigo] = {"estado": "bloqueado", "detalhe": f"{bs[0].tipo}: {bs[0].motivo or ''}".strip(": ")}
            elif not letivo[i.unidade_id][0]:
                cel[t.codigo] = {"estado": "nao_letivo", "detalhe": letivo[i.unidade_id][1]}
            elif not na_jornada:
                cel[t.codigo] = {"estado": "fora_jornada"}
            else:
                cel[t.codigo] = {"estado": "livre"}
        linhas_i.append({"id": i.id, "nome": i.nome, "modalidade": i.modalidade, "unidade_id": i.unidade_id, "turnos": cel})
    linhas_a = []
    for a in ambs:
        cel = {}
        for t in [t for t in turnos if t.unidade_id == a.unidade_id]:
            ini, fim = janela(t)
            da = [x for x in aulas if x.ambiente_id == a.id and x.inicio < fim and x.fim > ini]
            bs = [b for b in bloqs if b.alvo_tipo == "ambiente" and b.alvo_id == a.id and b.inicio < fim and b.fim > ini]
            if da:
                cel[t.codigo] = {"estado": "aula", **desc_aula(da[0])}
            elif bs:
                cel[t.codigo] = {"estado": "bloqueado", "detalhe": f"{bs[0].tipo}: {bs[0].motivo or ''}".strip(": ")}
            elif a.situacao != "operacional":
                cel[t.codigo] = {"estado": "bloqueado", "detalhe": a.situacao}
            elif not letivo[a.unidade_id][0]:
                cel[t.codigo] = {"estado": "nao_letivo", "detalhe": letivo[a.unidade_id][1]}
            else:
                cel[t.codigo] = {"estado": "livre"}
        linhas_a.append({"id": a.id, "codigo": a.codigo, "nome": a.nome, "unidade_id": a.unidade_id, "turnos": cel})
    contagem = lambda linhas, est: sum(1 for l in linhas for c in l["turnos"].values() if c["estado"] == est)
    return {
        "data": dia.isoformat(), "dia_semana": DIAS[dia.weekday()],
        "turnos": [{"codigo": c, "nome": n} for c, n in dict((t.codigo, t.nome) for t in turnos).items()],
        "nao_letivo": {str(u): m for u, (ok, m) in letivo.items() if not ok},
        "instrutores": linhas_i, "salas": linhas_a,
        "resumo": {"instrutores_livres": contagem(linhas_i, "livre"), "instrutores_em_aula": contagem(linhas_i, "aula"),
                   "instrutores_pl_pj": contagem(linhas_i, "PL") + contagem(linhas_i, "PJ"), "instrutores_tr": contagem(linhas_i, "TR"), "instrutores_bloqueados": contagem(linhas_i, "bloqueado"),
                   "salas_livres": contagem(linhas_a, "livre"), "salas_ocupadas": contagem(linhas_a, "aula"), "salas_bloqueadas": contagem(linhas_a, "bloqueado")},
    }


# ----------------------------------------------------------------------------- ocupação dos instrutores (jornada)
def _horas_por_instrutor(db, cenario_id, d0, d1, ids):
    horas = defaultdict(float)
    semanas = defaultdict(lambda: defaultdict(float))
    if not ids:
        return horas, semanas
    for iid, data, mins in db.execute(select(Alocacao.instrutor_id, Alocacao.data, Alocacao.minutos_aula).where(
            Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada", Alocacao.instrutor_id.in_(ids),
            Alocacao.data >= d0, Alocacao.data <= d1)):
        horas[iid] += mins / 60
        semanas[iid][_seg(data)] += mins / 60
    return horas, semanas


def _n_semanas(d0, d1):
    return max(1, round(((d1 - d0).days + 1) / 7))


def ranking(db: Session, cenario_id: int, d0: date, d1: date, unidades=None, limite: int = 15) -> dict:
    """Maiores (e menores) ocupações no período: instrutores (da jornada), salas, áreas e turnos."""
    from app.services import indicadores
    insts = _instrutores(db, unidades)
    horas, semanas = _horas_por_instrutor(db, cenario_id, d0, d1, [i.id for i in insts])
    n = _n_semanas(d0, d1)
    areas = {a.id: a.nome for a in db.scalars(select(Area))}
    linhas = []
    for i in insts:
        carga = float(i.carga_horaria_contratual or 0)
        media = horas[i.id] / n
        pct = 100 * media / carga if carga else 0
        pico = max(semanas[i.id].values(), default=0)
        linhas.append({"id": i.id, "nome": i.nome, "area": areas.get(i.area_id), "modalidade": i.modalidade, "carga_h": carga,
                       "aula_media_semana_h": round(media, 1), "maior_semana_h": round(pico, 1), "ocupacao_pct": round(pct, 1),
                       "pico_pct": round(100 * pico / carga, 1) if carga else 0, "faixa": faixa(pct)})
    linhas.sort(key=lambda x: -x["ocupacao_pct"])
    amb = indicadores.ocupacao_ambientes(db, cenario_id, d0, d1, unidades_permitidas=unidades)
    salas = sorted([{"id": a["ambiente_id"], "codigo": a["codigo"], "nome": a["nome"], "tipo": a["tipo"], "horas_ocupadas": a["horas_ocupadas"],
                     "horas_disponiveis": a["horas_disponiveis"], "ocupacao_pct": a["taxa_ocupacao_pct"], "faixa": faixa(a["taxa_ocupacao_pct"])}
                    for a in amb["ambientes"]], key=lambda x: -x["ocupacao_pct"])
    por_area = defaultdict(lambda: [0.0, 0.0, 0])
    for l in linhas:
        por_area[l["area"] or "Sem área"][0] += l["aula_media_semana_h"]
        por_area[l["area"] or "Sem área"][1] += l["carga_h"]
        por_area[l["area"] or "Sem área"][2] += 1
    areas_rank = sorted([{"area": k, "instrutores": v[2], "ocupacao_pct": round(100 * v[0] / v[1], 1) if v[1] else 0,
                          "faixa": faixa(100 * v[0] / v[1] if v[1] else 0)} for k, v in por_area.items()], key=lambda x: -x["ocupacao_pct"])
    turnos = sorted([{"turno": t["turno"], "ocupacao_pct": t["taxa_ocupacao_pct"], "faixa": faixa(t["taxa_ocupacao_pct"])}
                     for t in amb["por_turno"]], key=lambda x: -x["ocupacao_pct"])
    dist = defaultdict(int)
    for l in linhas:
        dist[l["faixa"]] += 1
    return {"periodo": {"inicio": d0.isoformat(), "fim": d1.isoformat(), "semanas": n},
            "instrutores_mais": linhas[:limite], "instrutores_menos": [l for l in reversed(linhas)][:limite],
            "salas_mais": salas[:limite], "salas_menos": list(reversed(salas))[:limite], "areas": areas_rank, "turnos": turnos,
            "distribuicao_instrutores": dict(dist), "total_instrutores": len(linhas),
            "referencias": {"ideal_pct": OCUPACAO_IDEAL * 100, "teto_pct": OCUPACAO_MAXIMA * 100}}


def serie(db: Session, cenario_id: int, d0: date, d1: date, unidades=None, hoje: date | None = None) -> dict:
    """Ocupação semana a semana no intervalo (instrutores e salas). Semanas futuras = previsão pela grade gerada."""
    from app.services import indicadores
    hoje = hoje or date.today()
    insts = _instrutores(db, unidades)
    carga_total = sum(float(i.carga_horaria_contratual or 0) for i in insts)
    _h, semanas = _horas_por_instrutor(db, cenario_id, d0, d1, [i.id for i in insts])
    pontos = []
    s = _seg(d0)
    while s <= d1:
        fim = min(s + timedelta(days=6), d1)
        aula_h = sum(semanas[i.id].get(s, 0) for i in insts)
        acima = sum(1 for i in insts if float(i.carga_horaria_contratual or 0) and
                    semanas[i.id].get(s, 0) / float(i.carga_horaria_contratual) > OCUPACAO_MAXIMA + 1e-6)
        amb = indicadores.ocupacao_ambientes(db, cenario_id, max(s, d0), fim, unidades_permitidas=unidades)
        disp = sum(a["horas_disponiveis"] for a in amb["ambientes"]) or 0
        ocup = sum(a["horas_ocupadas"] for a in amb["ambientes"])
        pontos.append({"semana": s.isoformat(), "rotulo": f"{s:%d/%m}", "previsao": s > hoje,
                       "instrutores_pct": round(100 * aula_h / carga_total, 1) if carga_total else 0,
                       "salas_pct": round(100 * ocup / disp, 1) if disp else 0, "aulas_h": round(aula_h, 1), "instrutores_acima_teto": acima})
        s += timedelta(days=7)
    reais = [p for p in pontos if not p["previsao"]]
    futuras = [p for p in pontos if p["previsao"]]
    media = lambda ps, k: round(sum(p[k] for p in ps) / len(ps), 1) if ps else None
    return {"pontos": pontos, "media_realizada": {"instrutores_pct": media(reais, "instrutores_pct"), "salas_pct": media(reais, "salas_pct")},
            "media_prevista": {"instrutores_pct": media(futuras, "instrutores_pct"), "salas_pct": media(futuras, "salas_pct")},
            "pico": max(pontos, key=lambda p: p["instrutores_pct"], default=None),
            "referencias": {"ideal_pct": OCUPACAO_IDEAL * 100, "teto_pct": OCUPACAO_MAXIMA * 100}}


def serie_impacto(db: Session, cenario_id: int, d0: date, d1: date, unidades=None, hoje: date | None = None,
                  extras: list[tuple[date, date, float]] | None = None, cenario_com_id: int | None = None) -> dict:
    """Ocupação semana a semana sem e com a(s) turma(s) simulada(s), no recorte da turma.
    Com `cenario_com_id` (grade de teste montada) usa as aulas reais da simulação; senão soma às horas atuais a carga
    semanal estimada de cada UC simulada (`extras` = [(início, fim, horas por semana)]), em instrutores e em salas."""
    base = serie(db, cenario_id, d0, d1, unidades, hoje)
    com = serie(db, cenario_com_id, d0, d1, unidades, hoje) if cenario_com_id else None
    insts = _instrutores(db, unidades)
    carga_total = sum(float(i.carga_horaria_contratual or 0) for i in insts)
    from app.services import indicadores
    pontos = []
    for i, p in enumerate(base["pontos"]):
        s = date.fromisoformat(p["semana"])
        q = dict(p)
        if com:
            c = com["pontos"][i]
            q.update({"instrutores_pct_com": c["instrutores_pct"], "salas_pct_com": c["salas_pct"], "aulas_h_com": c["aulas_h"],
                      "instrutores_acima_teto_com": c["instrutores_acima_teto"]})
        else:
            fim_s = s + timedelta(days=6)
            add = sum(h for a, b, h in (extras or []) if a <= fim_s and b >= s)
            amb = indicadores.ocupacao_ambientes(db, cenario_id, max(s, d0), min(fim_s, d1), unidades_permitidas=unidades)
            disp = sum(a["horas_disponiveis"] for a in amb["ambientes"]) or 0
            ocup = sum(a["horas_ocupadas"] for a in amb["ambientes"])
            q.update({"instrutores_pct_com": round(100 * (p["aulas_h"] + add) / carga_total, 1) if carga_total else 0,
                      "salas_pct_com": round(100 * (ocup + add) / disp, 1) if disp else 0, "aulas_h_com": round(p["aulas_h"] + add, 1)})
        pontos.append(q)
    media = lambda k: round(sum(p[k] for p in pontos) / len(pontos), 1) if pontos else None
    pico = max(pontos, key=lambda p: p["instrutores_pct_com"], default=None)
    return {"pontos": pontos, "fonte": "grade_de_teste" if com else "estimativa",
            "media": {"instrutores_pct": media("instrutores_pct"), "instrutores_pct_com": media("instrutores_pct_com"),
                      "salas_pct": media("salas_pct"), "salas_pct_com": media("salas_pct_com")},
            "pico_com": pico, "semanas_acima_teto": sum(1 for p in pontos if p["instrutores_pct_com"] > OCUPACAO_MAXIMA * 100 + 1e-6),
            "semanas_acima_ideal": sum(1 for p in pontos if p["instrutores_pct_com"] > OCUPACAO_IDEAL * 100 + 1e-6),
            "periodo": {"inicio": d0.isoformat(), "fim": d1.isoformat()},
            "referencias": {"ideal_pct": OCUPACAO_IDEAL * 100, "teto_pct": OCUPACAO_MAXIMA * 100}}


# ----------------------------------------------------------------------------- quadro de instrutores
def divisao_nova_turma(turnos: int) -> list[int]:
    """Divisão preferida de uma turma nova em 2 UCs na semana (ex.: 5 turnos → 3 + 2). É uma opção, não uma regra."""
    turnos = max(1, int(turnos))
    return [turnos] if turnos == 1 else [math.ceil(turnos / 2), turnos // 2]


def encaixe_nova_turma(livres: dict[str, int], turnos: int) -> dict:
    """Cabe mais uma turma com `turnos` dias de aula por semana nos dias livres (até o teto de 90%) dos instrutores?
    Tenta a divisão 3 + 2 (uma UC por instrutor) e, se não der, qualquer divisão entre vários instrutores."""
    partes = divisao_nova_turma(turnos)
    ordem = sorted(((n, nome) for nome, n in livres.items() if n > 0), reverse=True)
    total = sum(n for n, _ in ordem)
    usados, plano = set(), []
    for parte in partes:  # maior parte primeiro: escolhe o instrutor com a menor folga que ainda comporta a parte
        cand = sorted((n, nome) for n, nome in ordem if n >= parte and nome not in usados)
        if not cand:
            plano = None
            break
        usados.add(cand[0][1])
        plano.append({"instrutor": cand[0][1], "turnos": parte})
    if plano:
        modo = "uma_uc" if len(partes) == 1 else "divisao_preferida"
    elif ordem and ordem[0][0] >= turnos:
        modo, plano = "um_instrutor", [{"instrutor": ordem[0][1], "turnos": turnos}]
    elif total >= turnos:
        modo, plano, falta = "dividida", [], turnos
        for n, nome in ordem:
            if falta <= 0:
                break
            plano.append({"instrutor": nome, "turnos": min(n, falta)})
            falta -= min(n, falta)
    else:
        modo, plano = "nao_cabe", []
    return {"turnos_semana": turnos, "divisao_preferida": partes, "cabe": modo != "nao_cabe", "modo": modo, "plano": plano,
            "turnos_livres_total": total, "instrutores_com_folga": len(ordem)}


def quadro_instrutores(db: Session, cenario_id: int, unidades=None, hoje: date | None = None, simulacao_id: int | None = None,
                       turmas_extra: dict[int, int] | None = None) -> dict:
    """Precisa contratar? Por área: demanda semanal de aulas daqui até o fim do semestre (grade gerada + carga ainda
    sem horário, inclusive turmas novas e, se pedido, as de uma simulação ou turmas hipotéticas) contra a capacidade
    do quadro (ideal 80% e teto 90% da jornada).

    - A capacidade da área conta os instrutores da área principal; um instrutor de outra área só entra se estiver
      alocado em turma desta área, e entra com a fração da jornada que dedica a ela.
    - Contratar vem da ocupação. A proporção de 5 instrutores para 4 turmas é um aviso, que pesa quando a folga dos
      instrutores não comporta mais uma turma (divisão preferida 3 + 2: duas UCs, uma com 3 dias e outra com 2)."""
    from app.services.planejamento import area_da_turma, nivel_atende, nivel_da_turma, situacao_carga_horaria
    from app.services.regras_aula import limite_letivo_efetivo
    cen = db.get(CenarioPlanejamento, cenario_id)
    hoje = hoje or date.today()
    fim = cen.periodo_fim or hoje + timedelta(days=120)
    ref = max(hoje, cen.periodo_inicio or hoje)
    semanas = max(1.0, ((fim - ref).days + 1) / 7)
    areas = {a.id: a for a in db.scalars(select(Area))}
    q = select(Turma).where(Turma.ativo.is_(True), Turma.situacao.notin_(["concluida", "cancelada"]), Turma.data_fim >= ref)
    q = q.where((Turma.simulacao_id.is_(None)) | (Turma.simulacao_id == simulacao_id)) if simulacao_id else q.where(Turma.simulacao_id.is_(None))
    if unidades is not None:
        q = q.where(Turma.unidade_id.in_(unidades))
    turmas = db.scalars(q).all()
    area_turma = {}

    def area_de(tid):
        if tid not in area_turma:
            t = db.get(Turma, tid)
            area_turma[tid] = area_da_turma(db, t) if t else None
        return area_turma[tid]

    dem = defaultdict(lambda: {"grade_h": 0.0, "sem_horario_h": 0.0, "turmas": set(), "simuladas": set(), "ritmo": [], "niveis": []})
    for t in turmas:
        a = area_de(t.id)
        d = dem[a]
        (d["simuladas"] if t.simulacao_id else d["turmas"]).add(t.codigo)
        d["niveis"].append(nivel_da_turma(db, t))
        futuras = db.execute(select(Alocacao.data, Alocacao.minutos_aula).where(Alocacao.cenario_id == cenario_id, Alocacao.turma_id == t.id,
                                                                            Alocacao.status != "cancelada", Alocacao.data >= ref)).all()
        por_sem = defaultdict(float)
        for dt, mins in futuras:
            por_sem[_seg(dt)] += mins / 60
        futuras = [m for _dt, m in futuras]
        h_sem_horario = 0.0
        for tuc in db.scalars(select(TurmaUC).where(TurmaUC.turma_id == t.id, TurmaUC.ativo.is_(True),
                                                    TurmaUC.situacao.notin_(["concluida", "cancelada"]))):
            sh = situacao_carga_horaria(db, cenario_id, tuc)["restante_h"]
            d["sem_horario_h"] += sh
            h_sem_horario += sh
        d["grade_h"] += sum(futuras) / 60
        # ritmo da turma em curso (h/semana nas semanas com aula; sem grade, a carga restante até o término):
        # base para o tamanho de uma turma nova da área
        if por_sem:
            d["ritmo"].append(sorted(por_sem.values())[len(por_sem) // 2])
        elif h_sem_horario > 0:
            d["ritmo"].append(h_sem_horario / max(1.0, ((min(t.data_fim, fim) - max(ref, t.data_inicio or ref)).days + 1) / 7))

    insts = _instrutores(db, unidades)
    ids = [i.id for i in insts]
    # horas de aula de cada instrutor, daqui ao fim do período, por área da turma
    h_area = defaultdict(lambda: defaultdict(float))
    if ids:
        for iid, tid, mins in db.execute(select(Alocacao.instrutor_id, Alocacao.turma_id, Alocacao.minutos_aula).where(
                Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada", Alocacao.instrutor_id.in_(ids),
                Alocacao.data >= ref, Alocacao.data <= fim)):
            h_area[iid][area_de(tid)] += mins / 60
    # fração da jornada de cada instrutor em cada área: só a principal, salvo se já dá aula em turma de outra área
    fracoes = defaultdict(list)  # area_id -> [(instrutor, fração)]
    for i in insts:
        outras = {a: h for a, h in h_area[i.id].items() if a != i.area_id and h > 0}
        tot = sum(h_area[i.id].values())
        if not outras or tot <= 0:
            fracoes[i.area_id].append((i, 1.0))
            continue
        resto = 1.0
        for a, h in outras.items():
            fracoes[a].append((i, h / tot))
            resto -= h / tot
        if resto > 1e-6:
            fracoes[i.area_id].append((i, resto))
    # turnos livres de cada instrutor por semana, até o teto de 90% (aulas já na grade, média por semana)
    livres_h = {i.id: max(0.0, limite_letivo_efetivo(i) - sum(h_area[i.id].values()) / semanas) for i in insts}

    linhas = []
    for aid in sorted(set(dem) | set(fracoes), key=lambda x: (areas[x].nome if x in areas else "~")):
        d = dem.get(aid) or {"grade_h": 0.0, "sem_horario_h": 0.0, "turmas": set(), "simuladas": set(), "ritmo": [], "niveis": []}
        n_turmas = len(d["turmas"]) + len(d["simuladas"])
        demanda = (d["grade_h"] + d["sem_horario_h"]) / semanas
        por_turma = demanda / n_turmas if n_turmas and demanda > 0 else 5 * HORAS_POR_TURNO  # sem histórico: 5 turnos (3 + 2)
        extra = (turmas_extra or {}).get(aid, 0)
        if extra:
            demanda += extra * por_turma
            n_turmas += extra
        equipe = fracoes.get(aid, [])
        principais = [i for i, _f in equipe if i.area_id == aid]
        de_outras = [{"nome": i.nome, "area_principal": areas[i.area_id].nome if i.area_id in areas else None, "fracao": round(f, 2),
                      "aula_semana_h": round(h_area[i.id][aid] / semanas, 1)} for i, f in equipe if i.area_id != aid]
        carga = sum(float(i.carga_horaria_contratual or 0) * f for i, f in equipe)
        cap_ideal, cap_teto = carga * OCUPACAO_IDEAL, carga * OCUPACAO_MAXIMA
        ocup = 100 * demanda / carga if carga else (999.0 if demanda else 0.0)
        # quanto falta em instrutores de 40 h para a demanda ficar em 80% da jornada
        falta_h = max(0.0, demanda - cap_ideal)
        contratar_ocupacao = math.ceil(falta_h / (40 * OCUPACAO_IDEAL) - 1e-9) if falta_h > 0.05 else 0
        # cabe mais uma turma? folga até o teto de cada instrutor, descontada a carga da área ainda sem horário
        sem_horario_sem = d["sem_horario_h"] / semanas + (extra * por_turma if extra else 0)
        # nível da turma nova típica da área: técnico se a maioria das turmas é técnica (ou se a área ainda não tem turmas)
        niveis = d.get("niveis") or []
        nivel_nova = "basico" if niveis and niveis.count("basico") > niveis.count("tecnico") else "tecnico"
        folga = {i.nome: livres_h[i.id] * f for i, f in equipe if nivel_atende(i.nivel, nivel_nova)}
        soma = sum(folga.values())
        fator = max(0.0, (soma - sem_horario_sem) / soma) if soma > 0 else 0.0
        livres = {n: int(h * fator // HORAS_POR_TURNO + 1e-9) for n, h in folga.items()}
        ritmo = sorted(d.get("ritmo") or [])
        ritmo_h = ritmo[len(ritmo) // 2] if ritmo else 5 * HORAS_POR_TURNO
        turnos_nova = max(1, min(10, round(ritmo_h / HORAS_POR_TURNO)))
        encaixe = encaixe_nova_turma(livres, turnos_nova)
        encaixe["nivel"] = nivel_nova
        encaixe["faltam_turnos"] = max(0, turnos_nova - encaixe["turnos_livres_total"]) if not encaixe["cabe"] else 0
        n_equipe = round(sum(f for _i, f in equipe), 1)
        ideal_proporcao = math.ceil(n_turmas * INSTRUTORES_POR_TURMA - 1e-9)
        deficit_proporcao = max(0, math.ceil(ideal_proporcao - n_equipe - 0.1 - 1e-6))  # tolera frações de instrutores compartilhados
        if not equipe and demanda:
            situacao = "sem_instrutor"
        elif ocup > OCUPACAO_MAXIMA * 100 + 1e-6:
            situacao = "contratar"
        elif ocup > OCUPACAO_IDEAL * 100 + 1e-6 or (n_turmas and not encaixe["cabe"]):
            situacao = "atencao"
        elif ocup < 50 and equipe:
            situacao = "ociosa"
        else:
            situacao = "adequado"
        aviso = None
        if deficit_proporcao and n_turmas:
            eq = f"{n_equipe:g}".replace(".", ",")
            aviso = {"nivel": "forte" if not encaixe["cabe"] else "leve", "faltam": deficit_proporcao,
                     "texto": f"proporção 5:4 abaixo da referência ({eq} instrutores para {n_turmas} turma(s); referência {ideal_proporcao}). "
                              + ("Sem folga para mais uma turma: contrate ou habilite instrutor de outra área."
                                 if not encaixe["cabe"] else "A folga atual ainda comporta uma nova turma.")}
        linhas.append({
            "area_id": aid, "area": areas[aid].nome if aid in areas else "Sem área",
            "turmas": n_turmas, "turmas_lista": sorted(d["turmas"]), "turmas_simuladas": sorted(d["simuladas"]), "turmas_hipoteticas": extra,
            "instrutores": len(principais), "instrutores_outras_areas": de_outras,
            "instrutores_basicos": sum(1 for i in principais if i.nivel == "basico"),
            "instrutores_tecnicos": sum(1 for i in principais if i.nivel != "basico"),
            "turmas_tecnicas": niveis.count("tecnico"), "turmas_basicas": niveis.count("basico"), "instrutores_equivalentes": n_equipe,
            "instrutores_40h_equivalentes": round(carga / 40, 1),
            "razao_instrutores_turma": round(n_equipe / n_turmas, 2) if n_turmas else None,
            "ideal_proporcao": ideal_proporcao, "demanda_semana_h": round(demanda, 1), "na_grade_h": round(d["grade_h"] / semanas, 1),
            "sem_horario_semana_h": round(d["sem_horario_h"] / semanas, 1), "capacidade_ideal_h": round(cap_ideal, 1),
            "capacidade_teto_h": round(cap_teto, 1), "ocupacao_projetada_pct": round(min(ocup, 999), 1), "faixa": faixa(ocup),
            "contratar_por_ocupacao": contratar_ocupacao, "contratar_por_proporcao": deficit_proporcao,
            "contratar_recomendado": contratar_ocupacao if situacao in ("contratar", "sem_instrutor") else 0,
            "contratar_para_nova_turma": 0 if encaixe["cabe"] else 1,
            "nova_turma": encaixe, "aviso_proporcao": aviso, "situacao": situacao,
        })
    tot = lambda k: round(sum(l[k] for l in linhas), 1)
    total = {"turmas": sum(l["turmas"] for l in linhas), "instrutores": len(insts),
             "demanda_semana_h": tot("demanda_semana_h"), "capacidade_ideal_h": tot("capacidade_ideal_h"), "capacidade_teto_h": tot("capacidade_teto_h"),
             "contratar_recomendado": sum(l["contratar_recomendado"] for l in linhas),
             "areas_sem_encaixe": [l["area"] for l in linhas if l["turmas"] and not l["nova_turma"]["cabe"]],
             "avisos_proporcao": sum(1 for l in linhas if l["aviso_proporcao"])}
    carga_total = sum(float(i.carga_horaria_contratual or 0) for i in insts)
    total["ocupacao_projetada_pct"] = round(100 * total["demanda_semana_h"] / carga_total, 1) if carga_total else 0
    total["razao_instrutores_turma"] = round(total["instrutores"] / total["turmas"], 2) if total["turmas"] else None
    return {"referencia": ref.isoformat(), "fim": fim.isoformat(), "semanas_restantes": round(semanas, 1), "areas": linhas, "total": total,
            "parametros": {"ideal_pct": OCUPACAO_IDEAL * 100, "teto_pct": OCUPACAO_MAXIMA * 100, "instrutores_por_turma": INSTRUTORES_POR_TURMA,
                           "horas_por_turno": HORAS_POR_TURNO},
            "explicacao": "Demanda = aulas já na grade daqui até o fim do semestre + carga ainda sem horário, por semana. "
                          "Capacidade = jornada dos instrutores da área (ideal 80%, teto 90%); instrutor de outra área só conta se já dá aula "
                          "em turma desta área, e com a fração que dedica a ela. Contratar = instrutores de 40 h que faltam para a área ficar em 80%. "
                          "Nova turma = cabe mais uma turma nos dias de aula livres dos instrutores até 90%, de preferência dividida em 2 UCs (ex.: 3 + 2 dias). "
                          "A proporção 5 instrutores : 4 turmas aparece como aviso."}
