"""Avaliação da função objetivo sobre as aulas datadas de um cenário.

É a régua oficial para comparar cenários: todos os cenários comparados são
avaliados com o mesmo conjunto de pesos, e cada valor bruto é normalizado
por semana (média das semanas com aulas), para que cenários com horizontes
diferentes sejam comparáveis. A pontuação total é Σ peso × valor bruto.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alocacao,
    Ambiente,
    CenarioPlanejamento,
    Instrutor,
    PeriodoHorario,
    TipoAmbiente,
    Turma,
    UnidadeCurricular,
)
from app.solver.criterios import CRITERIOS, normalizar_pesos


def _semanas(datas) -> int:
    if not datas:
        return 1
    semanas = {d - timedelta(days=d.weekday()) for d in datas}
    return max(len(semanas), 1)


def avaliar_cenario(db: Session, cenario_id: int, pesos: dict | None = None, referencia_id: int | None = None) -> dict:
    pesos = normalizar_pesos(pesos)
    aulas = db.scalars(select(Alocacao).where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada")).all()
    n_sem = _semanas([a.data for a in aulas])
    turmas = {t.id: t for t in db.scalars(select(Turma).where(Turma.id.in_({a.turma_id for a in aulas})))} if aulas else {}
    ambientes = {a.id: a for a in db.scalars(select(Ambiente))}
    tipos = {t.id: t for t in db.scalars(select(TipoAmbiente))}
    instrutores = {i.id: i for i in db.scalars(select(Instrutor))}
    ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({a.uc_id for a in aulas})))} if aulas else {}
    periodos = db.scalars(select(PeriodoHorario).where(PeriodoHorario.ativo.is_(True))).all()
    excepcionais = [(p.unidade_id, p.hora_inicio, p.hora_fim, set(p.dias_semana or [])) for p in periodos if p.excepcional]
    duracao_periodo = (sum((p.hora_fim.hour * 60 + p.hora_fim.minute) - (p.hora_inicio.hour * 60 + p.hora_inicio.minute) for p in periodos) / len(periodos)) if periodos else 50

    v = defaultdict(float)

    def janelas(chave_fn):
        por = defaultdict(list)
        for a in aulas:
            k = chave_fn(a)
            if k is not None:
                por[(k, a.data)].append(a)
        total = 0.0
        for lst in por.values():
            lst.sort(key=lambda a: a.inicio)
            for a1, a2 in zip(lst, lst[1:]):
                gap = (a2.inicio - a1.fim).total_seconds() / 60
                # só conta janelas dentro do mesmo turno (lacunas < 3 h)
                if 0 < gap < 180:
                    total += gap / duracao_periodo
        return total / n_sem

    v["janelas_instrutores"] = janelas(lambda a: a.instrutor_id)
    v["janelas_turmas"] = janelas(lambda a: a.turma_id if a.grupo is None else None)

    ociosidade = []
    espec = 0
    for a in aulas:
        amb = ambientes.get(a.ambiente_id)
        t = turmas.get(a.turma_id)
        if not amb or not t:
            continue
        tam = t.qtd_alunos if a.grupo is None else math.ceil(t.qtd_alunos / max(t.num_grupos, 1))
        ociosidade.append(max(0.0, 100 * (amb.capacidade_operacional - tam) / amb.capacidade_operacional))
        uc = ucs.get(a.uc_id)
        tipo = tipos.get(amb.tipo_ambiente_id)
        if tipo and tipo.especializado and uc and any(not tt.especializado for tt in uc.tipos_ambiente):
            espec += 1
    v["ocupacao_inadequada"] = (sum(ociosidade) / len(ociosidade)) if ociosidade else 0.0
    v["especializado_desnecessario"] = espec / n_sem

    # deslocamentos e concentração
    unidades_dia = defaultdict(set)
    for a in aulas:
        if a.instrutor_id and a.ambiente_id in ambientes:
            unidades_dia[(a.instrutor_id, a.data)].add(ambientes[a.ambiente_id].unidade_id)
    v["deslocamentos"] = sum(len(s) - 1 for s in unidades_dia.values() if len(s) > 1) / n_sem
    mesmo_dia = defaultdict(int)
    for a in aulas:
        mesmo_dia[(a.turma_uc_id, a.grupo, a.data)] += 1
    v["concentracao_dias"] = sum(n - 1 for n in mesmo_dia.values() if n > 1) / n_sem

    # equilíbrio: maior ocupação semanal média (% do limite letivo)
    carga = defaultdict(float)
    for a in aulas:
        if a.instrutor_id:
            carga[a.instrutor_id] += a.minutos_aula
    ocup = [100 * (mins / n_sem) / (float(instrutores[i].limite_ch_letiva) * 60) for i, mins in carga.items()
            if i in instrutores and float(instrutores[i].limite_ch_letiva) > 0]
    v["equilibrio_carga"] = max(ocup) if ocup else 0.0

    pref = 0
    for a in aulas:
        inst = instrutores.get(a.instrutor_id)
        t = turmas.get(a.turma_id)
        if inst and t and inst.turno_preferencial_id and t.turno_id and inst.turno_preferencial_id != t.turno_id:
            pref += 1
    v["preferencia_turno"] = pref / n_sem

    minp = int(pesos.get("min_periodos_dia", 2))
    dia_turma = defaultdict(float)
    for a in aulas:
        dia_turma[(a.turma_id, a.data)] += a.minutos_aula / duracao_periodo
    v["aulas_isoladas"] = sum(1 for n in dia_turma.values() if n < minp - 1e-6) / n_sem

    exc = 0
    for a in aulas:
        amb = ambientes.get(a.ambiente_id)
        u = amb.unidade_id if amb else None
        if a.data.weekday() >= 5 or any(un == u and a.data.weekday() in dias and a.inicio.time() < hf and hi < a.fim.time()
                                         for un, hi, hf, dias in excepcionais):
            exc += 1
    v["horarios_excepcionais"] = exc / n_sem

    # mudanças em relação à referência (cenário vigente)
    if referencia_id is None:
        cen = db.get(CenarioPlanejamento, cenario_id)
        pub = db.scalars(select(CenarioPlanejamento).where(CenarioPlanejamento.estado == "publicado",
                                                           CenarioPlanejamento.id != cenario_id)).first()
        referencia_id = pub.id if pub and cen and cen.tipo != "simulacao" else (pub.id if pub else None)
    if referencia_id:
        ref = {(a.turma_uc_id, a.grupo, a.data, a.inicio, a.instrutor_id, a.ambiente_id)
               for a in db.scalars(select(Alocacao).where(Alocacao.cenario_id == referencia_id, Alocacao.status != "cancelada"))}
        atual = {(a.turma_uc_id, a.grupo, a.data, a.inicio, a.instrutor_id, a.ambiente_id) for a in aulas}
        tucs_comuns = {k[0] for k in ref} & {k[0] for k in atual}
        v["mudancas_vigente"] = len({k for k in ref if k[0] in tucs_comuns} ^ {k for k in atual if k[0] in tucs_comuns}) / 2 / n_sem
    else:
        v["mudancas_vigente"] = 0.0
    v["preservar_aprovados"] = 0.0  # só faz sentido dentro de uma execução do solver
    v["demanda_nao_atendida"] = 0.0
    v["prazos"] = 0.0

    criterios = []
    total = 0.0
    for k, (unidade, desc, _p) in CRITERIOS.items():
        bruto = round(v.get(k, 0.0), 3)
        pts = round(pesos[k] * bruto, 3)
        total += pts
        criterios.append({"criterio": k, "descricao": desc, "unidade": unidade, "valor_bruto": bruto, "peso": pesos[k], "pontos": pts})
    return {"cenario_id": cenario_id, "pontuacao_total": round(total, 3), "criterios": criterios, "pesos": pesos,
            "semanas_avaliadas": n_sem, "aulas": len(aulas), "referencia_id": referencia_id,
            "escala": "pontos = peso × valor bruto; menor é melhor; valores brutos normalizados por semana com aulas"}
