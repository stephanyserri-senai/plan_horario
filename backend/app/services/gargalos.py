"""Análise de gargalos de capacidade (base semanal).

Ambientes e instrutores NÃO são somados indiscriminadamente: a capacidade é
calculada por fluxo máximo em um grafo demanda → recursos compatíveis
(tipo de ambiente, capacidade, turno, habilitação). O déficit é a parte da
demanda que nenhum recurso compatível consegue absorver, mesmo na melhor
distribuição possível. É uma análise agregada: ausência de déficit não
garante a existência de uma grade (isso só o gerador de horários comprova).

Tipos de déficit:
- deficit_capacidade_total     ambientes compatíveis insuficientes em qualquer turno
- deficit_turno                ambientes compatíveis insuficientes no turno da turma
- deficit_habilitacao          instrutores habilitados/disponíveis insuficientes
- conflito_distribuicao        demanda semanal da turma maior que os períodos da turma
- indisponibilidade_equipamentos  recursos móveis insuficientes
- inviabilidade_calendario     carga restante maior que o tempo letivo até o prazo
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services import fluxo as max_flow
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Ambiente,
    CompetenciaInstrutor,
    DisponibilidadeAmbiente,
    DisponibilidadeInstrutor,
    Instrutor,
    PeriodoHorario,
    Recurso,
    TipoAmbiente,
    Turma,
    TurmaUC,
    Turno,
    UnidadeCurricular,
)
from app.services.calendario import Calendarios, minutos

# Contagem de carga horária vigente na análise (hora-aula: cada período vale 60 min de CH).
_HORA_AULA = {"ativo": False}


def _fator(p) -> float:
    """Converte minutos de relógio de um período em minutos de carga horária."""
    dur = minutos(p.hora_fim) - minutos(p.hora_inicio)
    return 60 / dur if _HORA_AULA["ativo"] and dur > 0 else 1.0
from app.services.planejamento import ambientes_compativeis, instrutores_elegiveis, situacao_carga_horaria


@dataclass
class Demanda:
    chave: str
    turma_id: int
    turma_codigo: str
    turno_id: int | None
    unidade_id: int
    uc_id: int
    uc_codigo: str
    horas_semana: float
    tamanho: int
    tipos: frozenset
    ambientes: list[int]
    instrutores: list[int]
    recursos_moveis: dict = field(default_factory=dict)
    restante_h: float = 0.0
    data_inicio: date | None = None
    data_limite: date | None = None
    virtual: bool = False


def _horas_turno_ambiente(db, amb: Ambiente, turno_id: int, periodos: list[PeriodoHorario]) -> float:
    disp = db.scalars(select(DisponibilidadeAmbiente).where(DisponibilidadeAmbiente.ambiente_id == amb.id)).all()
    total = 0
    for p in periodos:
        if p.turno_id != turno_id:
            continue
        for d in p.dias_semana or []:
            ini, fim = minutos(p.hora_inicio), minutos(p.hora_fim)
            if disp:
                total += _fator(p) * sum(max(0, min(fim, minutos(j.hora_fim)) - max(ini, minutos(j.hora_inicio))) for j in disp if j.dia_semana == d)
            else:
                total += _fator(p) * (fim - ini)
    return total / 60


def _horas_turno_instrutor(janelas, turno: Turno, periodos: list[PeriodoHorario]) -> float:
    total = 0
    for p in periodos:
        if p.turno_id != turno.id:
            continue
        for d in p.dias_semana or []:
            ini, fim = minutos(p.hora_inicio), minutos(p.hora_fim)
            total += _fator(p) * max((max(0, min(fim, minutos(j.hora_fim)) - max(ini, minutos(j.hora_inicio))) for j in janelas if j.dia_semana == d), default=0)
    return total / 60


def demandas_do_cenario(db: Session, cenario_id: int | None, d0: date, d1: date, unidade_id=None, simulacao_id=None) -> list[Demanda]:
    q = select(TurmaUC).join(Turma).where(TurmaUC.ativo.is_(True), Turma.ativo.is_(True),
                                          TurmaUC.situacao.notin_(["concluida", "cancelada"]),
                                          Turma.situacao.notin_(["concluida", "cancelada"]))
    q = q.where((Turma.simulacao_id.is_(None)) | (Turma.simulacao_id == simulacao_id)) if simulacao_id else q.where(Turma.simulacao_id.is_(None))
    if unidade_id:
        q = q.where(Turma.unidade_id == unidade_id)
    res = []
    for tuc in db.scalars(q):
        turma = db.get(Turma, tuc.turma_id)
        uc = db.get(UnidadeCurricular, tuc.uc_id)
        ini = tuc.data_inicio or turma.data_inicio
        fim = tuc.data_limite or turma.data_fim
        if fim < d0 or ini > d1:
            continue
        info = situacao_carga_horaria(db, cenario_id, tuc)
        grupos = turma.num_grupos if (uc.divide_grupos and turma.num_grupos > 1) else 1
        tamanho = math.ceil(turma.qtd_alunos / grupos)
        horas = uc.encontros_semanais * info["horas_por_encontro"]
        ambs = ambientes_compativeis(db, uc, turma, grupos > 1)
        insts = instrutores_elegiveis(db, uc, turma.unidade_id, d0)
        for g in range(grupos):
            res.append(Demanda(
                chave=f"{tuc.id}:{g + 1 if grupos > 1 else 0}", turma_id=turma.id, turma_codigo=turma.codigo, turno_id=turma.turno_id,
                unidade_id=turma.unidade_id, uc_id=uc.id, uc_codigo=uc.codigo, horas_semana=horas, tamanho=tamanho,
                tipos=frozenset(t.id for t in uc.tipos_ambiente), ambientes=[a["id"] for a in ambs], instrutores=[i["id"] for i in insts],
                recursos_moveis={a["id"]: a["requer_recursos_moveis"] for a in ambs},
                restante_h=info["restante_h"], data_inicio=ini, data_limite=fim))
    return res


def analisar(db: Session, cenario_id: int | None, d0: date, d1: date, unidade_id=None, demandas_extras: list[Demanda] | None = None,
             simulacao_id=None, data_referencia: date | None = None, horas_extra_ambiente: dict[int, float] | None = None) -> dict:
    from app.services.regras_aula import hora_aula, regras_aula
    _HORA_AULA["ativo"] = hora_aula(regras_aula(db))
    demandas = demandas_do_cenario(db, cenario_id, d0, d1, unidade_id, simulacao_id) + list(demandas_extras or [])
    data_referencia = data_referencia or d0
    turnos = {t.id: t for t in db.scalars(select(Turno).where(Turno.ativo.is_(True)))}
    periodos = db.scalars(select(PeriodoHorario).where(PeriodoHorario.ativo.is_(True))).all()
    per_un = defaultdict(list)
    for p in periodos:
        per_un[p.unidade_id].append(p)
    tipos = {t.id: t for t in db.scalars(select(TipoAmbiente))}
    ambientes = {a.id: a for a in db.scalars(select(Ambiente).where(Ambiente.ativo.is_(True), Ambiente.situacao == "operacional"))}
    instrutores = {i.id: i for i in db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True), Instrutor.situacao == "ativo"))}
    gargalos = []

    # ------------------------------------------------------------------ ambientes por turno (fluxo)
    cap_amb_turno: dict[tuple[int, int], float] = {}
    for amb in ambientes.values():
        for t in {p.turno_id for p in per_un[amb.unidade_id]}:
            cap_amb_turno[(amb.id, t)] = _horas_turno_ambiente(db, amb, t, per_un[amb.unidade_id]) + (horas_extra_ambiente or {}).get(amb.id, 0.0)

    def fluxo_ambientes(dems: list[Demanda], turno_de) -> dict[str, float]:
        mf = max_flow.SimpleMaxFlow()
        n = {"s": 0, "t": 1}

        def no(k):
            if k not in n:
                n[k] = len(n)
            return n[k]
        for d in dems:
            mf.add_arc_with_capacity(n["s"], no(("d", d.chave)), int(round(d.horas_semana * 60)))
            for a in d.ambientes:
                for t in turno_de(d):
                    if (a, t) in cap_amb_turno:
                        mf.add_arc_with_capacity(no(("d", d.chave)), no(("a", a, t)), int(round(d.horas_semana * 60)))
        for (a, t), h in cap_amb_turno.items():
            if ("a", a, t) in n:
                mf.add_arc_with_capacity(n[("a", a, t)], n["t"], int(round(h * 60)))
        mf.solve(n["s"], n["t"])
        atendido = defaultdict(float)
        for i in range(mf.num_arcs()):
            if mf.tail(i) == n["s"]:
                chave = next(k for k, v in n.items() if v == mf.head(i))[1]
                atendido[chave] = mf.flow(i) / 60
        return atendido

    turnos_un = defaultdict(set)
    for p in periodos:
        turnos_un[p.unidade_id].add(p.turno_id)
    atend_turno = fluxo_ambientes(demandas, lambda d: [d.turno_id] if d.turno_id else sorted(turnos_un[d.unidade_id]))
    atend_total = fluxo_ambientes(demandas, lambda d: sorted(turnos_un[d.unidade_id]))

    grupos_tipo = defaultdict(list)
    for d in demandas:
        grupos_tipo[(d.tipos, d.turno_id)].append(d)
    for (tipos_set, turno_id), dems in grupos_tipo.items():
        dem_h = sum(d.horas_semana for d in dems)
        at_turno = sum(atend_turno[d.chave] for d in dems)
        at_total = sum(atend_total[d.chave] for d in dems)
        nomes = ", ".join(sorted(tipos[t].nome for t in tipos_set if t in tipos)) or "qualquer tipo"
        compat = sorted({a for d in dems for a in d.ambientes})
        oferta = sum(cap_amb_turno.get((a, turno_id), 0) for a in compat) if turno_id else sum(
            v for (a, t), v in cap_amb_turno.items() if a in compat)
        turno_nome = turnos[turno_id].nome if turno_id in turnos else "todos os turnos"
        if dem_h - at_turno > 0.05:
            deficit = dem_h - at_turno
            sobra_outros = at_total - at_turno
            alternativas = []
            if sobra_outros > 0.01:
                alternativas.append(f"Alterar o turno de parte das turmas: em outros turnos há capacidade compatível para absorver {sobra_outros:.1f} h semanais.")
            alternativas.append(f"Ampliar a disponibilidade dos ambientes compatíveis ({', '.join(ambientes[a].codigo for a in compat if a in ambientes) or 'nenhum'}) em {deficit:.1f} h semanais.")
            outros_tipos = [t.nome for t in tipos.values() if t.id not in tipos_set and not t.especializado]
            if not tipos_set or any(not tipos[t].especializado for t in tipos_set if t in tipos):
                alternativas.append(f"Avaliar se a UC aceita outros tipos de ambiente tecnicamente compatíveis ({', '.join(outros_tipos[:4])}).")
            alternativas.append("Redistribuir a carga semanal (mais semanas com menos encontros) ou redimensionar a oferta.")
            tipo_def = "deficit_turno" if dem_h - at_total <= 0.05 else "deficit_capacidade_total"
            gargalos.append({
                "tipo": tipo_def, "recurso": f"Ambientes: {nomes}", "turno": turno_nome,
                "descricao": f"Há demanda de {dem_h:.1f} horas semanais para atividades que exigem {nomes} no turno {turno_nome}, mas a disponibilidade compatível atendível é de {at_turno:.1f} horas. Déficit estimado: {deficit:.1f} horas semanais.",
                "demanda_h": round(dem_h, 1), "oferta_h": round(oferta, 1), "atendivel_h": round(at_turno, 1), "deficit_h": round(deficit, 1),
                "calculo": "Demanda = Σ (encontros semanais × horas por encontro) das turmas×UC ativas no período. Oferta atendível = fluxo máximo das demandas para os ambientes compatíveis (tipo, capacidade física, acessibilidade e equipamentos) com horas disponíveis no turno, sem somar ambientes não intercambiáveis.",
                "itens": [{"turma": d.turma_codigo, "uc": d.uc_codigo, "horas_semana": round(d.horas_semana, 2), "atendivel": round(atend_turno[d.chave], 2), "virtual": d.virtual} for d in dems],
                "ambientes_compativeis": [ambientes[a].codigo for a in compat if a in ambientes], "alternativas": alternativas,
            })

    # ------------------------------------------------------------------ instrutores (fluxo com turno)
    disp_inst = defaultdict(list)
    for j in db.scalars(select(DisponibilidadeInstrutor)):
        disp_inst[j.instrutor_id].append(j)
    mf = max_flow.SimpleMaxFlow()
    nos = {"s": 0, "t": 1}

    def no(k):
        if k not in nos:
            nos[k] = len(nos)
        return nos[k]
    for d in demandas:
        cap = int(round(d.horas_semana * 60))
        mf.add_arc_with_capacity(0, no(("d", d.chave)), cap)
        tlist = [d.turno_id] if d.turno_id else sorted(turnos_un[d.unidade_id])
        for i in d.instrutores:
            for t in tlist:
                if t in turnos:
                    mf.add_arc_with_capacity(no(("d", d.chave)), no(("it", i, t)), cap)
    for k, idx in list(nos.items()):
        if isinstance(k, tuple) and k[0] == "it":
            _, i, t = k
            inst = instrutores.get(i)
            if inst is None:
                continue
            h = _horas_turno_instrutor(disp_inst[i], turnos[t], per_un[turnos[t].unidade_id])
            mf.add_arc_with_capacity(idx, no(("i", i)), int(round(h * 60)))
    for k, idx in list(nos.items()):
        if isinstance(k, tuple) and k[0] == "i":
            mf.add_arc_with_capacity(idx, 1, int(round(float(instrutores[k[1]].limite_ch_letiva) * 60)))
    mf.solve(0, 1)
    atend_i = defaultdict(float)
    inv = {v: k for k, v in nos.items()}
    for a in range(mf.num_arcs()):
        if mf.tail(a) == 0:
            atend_i[inv[mf.head(a)][1]] = mf.flow(a) / 60
    por_uc = defaultdict(list)
    for d in demandas:
        por_uc[d.uc_id].append(d)
    for uc_id, dems in por_uc.items():
        dem_h = sum(d.horas_semana for d in dems)
        at = sum(atend_i[d.chave] for d in dems)
        if dem_h - at > 0.05:
            uc = db.get(UnidadeCurricular, uc_id)
            elegiveis = sorted({i for d in dems for i in d.instrutores})
            em_formacao = db.scalars(select(Instrutor.nome).join(CompetenciaInstrutor, CompetenciaInstrutor.instrutor_id == Instrutor.id)
                                     .where(CompetenciaInstrutor.uc_id == uc_id, CompetenciaInstrutor.nivel == "em_formacao")).all()
            alternativas = []
            if em_formacao:
                alternativas.append(f"Concluir a habilitação de instrutores 'em formação' na UC: {', '.join(em_formacao)}.")
            if elegiveis:
                alternativas.append("Ampliar a disponibilidade dos instrutores habilitados no turno da turma ou redistribuir aulas entre eles.")
            alternativas.append("Habilitar (matriz de competências) ou contratar instrutores para a UC.")
            gargalos.append({
                "tipo": "deficit_habilitacao", "recurso": f"Instrutores habilitados em {uc.codigo} – {uc.nome}", "turno": None,
                "descricao": f"A UC {uc.codigo} demanda {dem_h:.1f} h semanais, mas os instrutores habilitados ({len(elegiveis)}) conseguem absorver {at:.1f} h considerando disponibilidade por turno e limites letivos. Déficit estimado: {dem_h - at:.1f} h semanais.",
                "demanda_h": round(dem_h, 1), "atendivel_h": round(at, 1), "deficit_h": round(dem_h - at, 1),
                "calculo": "Fluxo máximo: demanda → instrutores habilitados (matriz de competências válida) → disponibilidade do instrutor no turno → limite de carga letiva semanal. Instrutores compartilhados entre UCs são considerados uma única vez.",
                "itens": [{"turma": d.turma_codigo, "horas_semana": round(d.horas_semana, 2), "atendivel": round(atend_i[d.chave], 2), "virtual": d.virtual} for d in dems],
                "instrutores_habilitados": [instrutores[i].nome for i in elegiveis if i in instrutores], "alternativas": alternativas,
            })

    # ------------------------------------------------------------------ equipamentos móveis
    acervo = defaultdict(int)
    for r in db.scalars(select(Recurso).where(Recurso.movel.is_(True), Recurso.ativo.is_(True), Recurso.situacao == "disponivel")):
        acervo[(r.unidade_id, r.tipo)] += r.quantidade_total
    uso = defaultdict(float)
    for d in demandas:
        if not d.recursos_moveis:
            continue
        # o ambiente compatível que exige menos recursos móveis (melhor caso)
        melhor = min(d.recursos_moveis.values(), key=lambda req: sum(req.values()), default={})
        for tipo, q in melhor.items():
            uso[(d.unidade_id, tipo, d.turno_id)] += q * d.horas_semana
    for (un, tipo, turno_id), qh in uso.items():
        horas_turno = sum(_fator(p) * (minutos(p.hora_fim) - minutos(p.hora_inicio)) for p in per_un[un] if turno_id is None or p.turno_id == turno_id
                          for _d in (p.dias_semana or [])) / 60
        oferta = acervo[(un, tipo)] * horas_turno
        if qh > oferta + 0.01:
            gargalos.append({
                "tipo": "indisponibilidade_equipamentos", "recurso": f"Equipamento: {tipo}", "turno": turnos[turno_id].nome if turno_id in turnos else None,
                "descricao": f"São necessárias {qh:.1f} unidade·hora semanais de '{tipo}', mas o acervo móvel ({acervo[(un, tipo)]} un.) oferece {oferta:.1f} unidade·hora no turno.",
                "demanda_h": round(qh, 1), "oferta_h": round(oferta, 1), "deficit_h": round(qh - oferta, 1),
                "calculo": "Demanda = Σ quantidade exigida pela UC não suprida por equipamento fixo do ambiente × horas semanais. Oferta = quantidade do acervo móvel × horas de aula do turno.",
                "alternativas": [f"Disponibilizar {math.ceil((qh - oferta) / max(horas_turno, 0.1))} unidade(s) adicionais de '{tipo}' ou instalar equipamentos fixos em ambientes compatíveis."],
            })

    # ------------------------------------------------------------------ distribuição por turma e calendário
    cal = Calendarios(db)
    por_turma = defaultdict(list)
    for d in demandas:
        por_turma[d.turma_id].append(d)
    for turma_id, dems in por_turma.items():
        turma = db.get(Turma, turma_id) if not dems[0].virtual else None
        dias = (turma.dias_possiveis if turma else [0, 1, 2, 3, 4]) or []
        un = dems[0].unidade_id
        tlist = [dems[0].turno_id] if dems[0].turno_id else list(turnos_un[un])
        horas_turma = sum(_fator(p) * (minutos(p.hora_fim) - minutos(p.hora_inicio)) for p in per_un[un] if p.turno_id in tlist
                          for dd in (p.dias_semana or []) if dd in dias) / 60
        # demanda simultânea: pico de horas semanais entre UCs com janelas sobrepostas (grupos em paralelo contam uma vez)
        por_tuc = {}
        for d in dems:
            por_tuc.setdefault(d.chave.split(":")[0], d)
        pontos = sorted({d.data_inicio for d in por_tuc.values() if d.data_inicio})
        pico = 0.0
        for p in pontos or [d0]:
            pico = max(pico, sum(d.horas_semana for d in por_tuc.values() if (d.data_inicio or d0) <= p <= (d.data_limite or d1)))
        if pico > horas_turma + 0.01:
            gargalos.append({
                "tipo": "conflito_distribuicao", "recurso": f"Turma {dems[0].turma_codigo}", "turno": None,
                "descricao": f"A turma {dems[0].turma_codigo} precisa de {pico:.1f} h semanais simultâneas, mas seu turno e dias permitidos oferecem {horas_turma:.1f} h.",
                "demanda_h": round(pico, 1), "oferta_h": round(horas_turma, 1), "deficit_h": round(pico - horas_turma, 1),
                "calculo": "Pico da soma das horas semanais das UCs com períodos de execução sobrepostos × horas de aula do turno nos dias permitidos.",
                "alternativas": ["Escalonar as UCs ao longo do período (sequência curricular).", "Ampliar os dias permitidos da turma.", "Reduzir encontros semanais e estender o período de execução."],
            })
        if turma is None:
            continue
        for d in por_tuc.values():
            if d.restante_h <= 0.01 or not d.data_limite:
                continue
            inicio = max(data_referencia, d.data_inicio or data_referencia)
            dias_letivos, x = 0, inicio
            while x <= d.data_limite:
                if x.weekday() in dias and cal.dia_letivo(turma, x)[0]:
                    dias_letivos += 1
                x += timedelta(days=1)
            horas_dia = horas_turma / max(len(dias), 1)
            maximo = dias_letivos * horas_dia
            semanas = dias_letivos / max(len(dias), 1)
            pedagogico = semanas * d.horas_semana
            if d.restante_h > maximo + 0.01:
                gargalos.append({
                    "tipo": "inviabilidade_calendario", "recurso": f"{d.turma_codigo} – {d.uc_codigo}", "turno": None,
                    "descricao": f"Restam {d.restante_h:.1f} h, mas até {d.data_limite:%d/%m/%Y} há apenas {dias_letivos} dia(s) letivo(s) ({maximo:.1f} h no máximo, ocupando todo o turno). Conclusão impossível no prazo.",
                    "demanda_h": round(d.restante_h, 1), "oferta_h": round(maximo, 1), "deficit_h": round(d.restante_h - maximo, 1),
                    "calculo": "Máximo = dias letivos restantes da turma até o prazo × horas de aula do turno por dia.",
                    "alternativas": ["Estender a data-limite da UC/turma.", "Autorizar dias letivos extras (exceção de calendário documentada)."],
                })
            elif d.restante_h > pedagogico + 0.01:
                gargalos.append({
                    "tipo": "inviabilidade_calendario", "recurso": f"{d.turma_codigo} – {d.uc_codigo}", "turno": None,
                    "descricao": f"Com {d.horas_semana:.1f} h semanais (encontros previstos), as {semanas:.1f} semanas letivas até {d.data_limite:%d/%m/%Y} comportam {pedagogico:.1f} h; restam {d.restante_h:.1f} h. Há risco de não conclusão pela restrição pedagógica de distribuição.",
                    "demanda_h": round(d.restante_h, 1), "oferta_h": round(pedagogico, 1), "deficit_h": round(d.restante_h - pedagogico, 1),
                    "calculo": "Capacidade pedagógica = semanas letivas restantes × encontros semanais × horas por encontro.",
                    "alternativas": [f"Aumentar a carga semanal para {d.restante_h / max(semanas, 0.1):.1f} h (mais encontros ou blocos maiores), se pedagogicamente aceitável.", "Estender a data-limite."],
                })

    resumo = defaultdict(lambda: {"quantidade": 0, "deficit_h": 0.0})
    for g in gargalos:
        resumo[g["tipo"]]["quantidade"] += 1
        resumo[g["tipo"]]["deficit_h"] = round(resumo[g["tipo"]]["deficit_h"] + g.get("deficit_h", 0), 1)
    return {
        "periodo": {"inicio": d0.isoformat(), "fim": d1.isoformat()},
        "demandas_consideradas": len(demandas), "demanda_total_h": round(sum(d.horas_semana for d in demandas), 1),
        "gargalos": sorted(gargalos, key=lambda g: -g.get("deficit_h", 0)), "resumo": dict(resumo),
        "observacao": "Análise agregada semanal. A inexistência de déficit não garante uma grade viável; a confirmação depende do gerador de horários.",
    }
