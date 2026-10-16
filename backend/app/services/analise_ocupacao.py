"""Consultas de situação, rankings, ocupação no tempo e análise do quadro de instrutores.

Ocupação da jornada (instrutor) = horas de aula na semana ÷ carga contratual semanal.
Referências da instituição: ideal até 80%, teto de 90% (40 h → 9 de 10 turnos; 20 h → 4 de 5).
Quadro de instrutores: o ideal é 5 instrutores para cada 4 turmas (1,25 por turma), o que dá folga para
distribuir aulas, planejamento e substituições.
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
            elif any(b.tipo in ("planejamento", "projeto") for b in bs):
                b = next(b for b in bs if b.tipo in ("planejamento", "projeto"))
                cel[t.codigo] = {"estado": "PL" if b.tipo == "planejamento" else "PJ", "detalhe": b.motivo}
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
                   "instrutores_pl_pj": contagem(linhas_i, "PL") + contagem(linhas_i, "PJ"), "instrutores_bloqueados": contagem(linhas_i, "bloqueado"),
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


# ----------------------------------------------------------------------------- quadro de instrutores
def quadro_instrutores(db: Session, cenario_id: int, unidades=None, hoje: date | None = None, simulacao_id: int | None = None,
                       turmas_extra: dict[int, int] | None = None) -> dict:
    """Precisa contratar? Por área: demanda semanal de aulas daqui até o fim do semestre (grade gerada + carga ainda
    sem horário, inclusive turmas novas e, se pedido, as de uma simulação ou turmas hipotéticas) contra a capacidade
    do quadro (ideal 80% e teto 90% da jornada) e contra a proporção ideal de 5 instrutores para 4 turmas."""
    from app.services.planejamento import situacao_carga_horaria
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
    dem = defaultdict(lambda: {"grade_h": 0.0, "sem_horario_h": 0.0, "turmas": set(), "simuladas": set()})
    for t in turmas:
        a = t.area_id
        d = dem[a]
        (d["simuladas"] if t.simulacao_id else d["turmas"]).add(t.codigo)
        futuras = db.execute(select(Alocacao.minutos_aula).where(Alocacao.cenario_id == cenario_id, Alocacao.turma_id == t.id,
                                                                 Alocacao.status != "cancelada", Alocacao.data >= ref)).scalars().all()
        d["grade_h"] += sum(futuras) / 60
        for tuc in db.scalars(select(TurmaUC).where(TurmaUC.turma_id == t.id, TurmaUC.ativo.is_(True),
                                                    TurmaUC.situacao.notin_(["concluida", "cancelada"]))):
            d["sem_horario_h"] += situacao_carga_horaria(db, cenario_id, tuc)["restante_h"]
    insts = _instrutores(db, unidades)
    por_area = defaultdict(list)
    for i in insts:
        por_area[i.area_id].append(i)
    linhas = []
    for aid in sorted(set(dem) | set(por_area), key=lambda x: (areas[x].nome if x in areas else "~")):
        d = dem.get(aid) or {"grade_h": 0.0, "sem_horario_h": 0.0, "turmas": set(), "simuladas": set()}
        n_turmas = len(d["turmas"]) + len(d["simuladas"])
        demanda = (d["grade_h"] + d["sem_horario_h"]) / semanas
        extra = (turmas_extra or {}).get(aid, 0)
        if extra:
            por_turma = demanda / n_turmas if n_turmas else 16.0  # sem histórico na área: 4 turnos por semana
            demanda += extra * por_turma
            n_turmas += extra
        equipe = por_area.get(aid, [])
        carga = sum(float(i.carga_horaria_contratual or 0) for i in equipe)
        cap_ideal, cap_teto = carga * OCUPACAO_IDEAL, carga * OCUPACAO_MAXIMA
        ocup = 100 * demanda / carga if carga else (999.0 if demanda else 0.0)
        # quanto falta em instrutores de 40 h para a demanda ficar em 80% da jornada
        falta_h = max(0.0, demanda - cap_ideal)
        contratar_ocupacao = math.ceil(falta_h / (40 * OCUPACAO_IDEAL) - 1e-9) if falta_h > 0.05 else 0
        ideal_proporcao = math.ceil(n_turmas * INSTRUTORES_POR_TURMA - 1e-9)
        contratar_proporcao = max(0, ideal_proporcao - len(equipe))
        if not equipe and demanda:
            situacao = "sem_instrutor"
        elif ocup > OCUPACAO_MAXIMA * 100 + 1e-6:
            situacao = "contratar"
        elif ocup > OCUPACAO_IDEAL * 100 + 1e-6 or contratar_proporcao:
            situacao = "atencao"
        elif ocup < 50 and equipe:
            situacao = "ociosa"
        else:
            situacao = "adequado"
        linhas.append({
            "area_id": aid, "area": areas[aid].nome if aid in areas else "Sem área",
            "turmas": n_turmas, "turmas_lista": sorted(d["turmas"]), "turmas_simuladas": sorted(d["simuladas"]), "turmas_hipoteticas": extra,
            "instrutores": len(equipe), "instrutores_40h_equivalentes": round(carga / 40, 1),
            "razao_instrutores_turma": round(len(equipe) / n_turmas, 2) if n_turmas else None,
            "ideal_proporcao": ideal_proporcao, "demanda_semana_h": round(demanda, 1), "na_grade_h": round(d["grade_h"] / semanas, 1),
            "sem_horario_semana_h": round(d["sem_horario_h"] / semanas, 1), "capacidade_ideal_h": round(cap_ideal, 1),
            "capacidade_teto_h": round(cap_teto, 1), "ocupacao_projetada_pct": round(min(ocup, 999), 1), "faixa": faixa(ocup),
            "contratar_por_ocupacao": contratar_ocupacao, "contratar_por_proporcao": contratar_proporcao,
            "contratar_recomendado": max(contratar_ocupacao, contratar_proporcao) if situacao in ("contratar", "sem_instrutor", "atencao") else 0,
            "situacao": situacao,
        })
    tot = lambda k: round(sum(l[k] for l in linhas), 1)
    total = {"turmas": sum(l["turmas"] for l in linhas), "instrutores": sum(l["instrutores"] for l in linhas),
             "demanda_semana_h": tot("demanda_semana_h"), "capacidade_ideal_h": tot("capacidade_ideal_h"), "capacidade_teto_h": tot("capacidade_teto_h"),
             "contratar_recomendado": sum(l["contratar_recomendado"] for l in linhas)}
    carga_total = sum(float(i.carga_horaria_contratual or 0) for i in insts)
    total["ocupacao_projetada_pct"] = round(100 * total["demanda_semana_h"] / carga_total, 1) if carga_total else 0
    total["razao_instrutores_turma"] = round(total["instrutores"] / total["turmas"], 2) if total["turmas"] else None
    return {"referencia": ref.isoformat(), "fim": fim.isoformat(), "semanas_restantes": round(semanas, 1), "areas": linhas, "total": total,
            "parametros": {"ideal_pct": OCUPACAO_IDEAL * 100, "teto_pct": OCUPACAO_MAXIMA * 100, "instrutores_por_turma": INSTRUTORES_POR_TURMA,
                           "horas_por_turno": HORAS_POR_TURNO},
            "explicacao": "Demanda = aulas já na grade daqui até o fim do semestre + carga ainda sem horário, por semana. "
                          "Capacidade = carga contratual dos instrutores da área (ideal 80%, teto 90%). "
                          "Contratar = instrutores de 40 h que faltam para a área ficar em 80%, ou para chegar a 5 instrutores a cada 4 turmas."}
