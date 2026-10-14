"""Modelo de geração de horários com Google OR-Tools CP-SAT.

Variáveis principais (por atividade k):
  c[k,o]    1 se a opção de horário o (dia + bloco de períodos) é usada
  x[k,o,i]  instrutor i no encontro da opção o
  y[k,o,r]  ambiente r no encontro da opção o
  v[k,i]    instrutor responsável pela atividade (o mesmo em toda a semana)

Restrições rígidas: quantidade de encontros, um instrutor/ambiente por
encontro, instrutor habilitado e disponível (filtrado na geração das opções),
ambiente compatível e disponível, não sobreposição de instrutor, ambiente
(com tempo de preparação), turma/grupos e recursos móveis, limites diários e
semanais do instrutor, descanso entre jornadas e tempo de deslocamento entre
unidades, e ocupações fixas.

As restrições de recurso só valem entre atividades cujas janelas de datas se
sobrepõem (fases), o que permite planejar UCs sequenciais da mesma turma.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.solver.contrato import (
    AtividadeS,
    Atribuicao,
    EntradaSolver,
    Janela,
    SaidaSolver,
)
from app.solver.criterios import normalizar_pesos

ESCALA = 10  # coeficientes inteiros = peso × ESCALA


@dataclass
class _Opcao:
    idx: int
    dia: int
    slots: list
    ini: int
    fim: int
    minutos: int
    turno_id: int
    unidade_id: int
    excepcional: bool


def _contem(janelas: list[Janela], dia: int, ini: int, fim: int) -> bool:
    return any(j.dia == dia and j.ini <= ini and fim <= j.fim for j in janelas)


def _opcoes(at: AtividadeS, grade: dict[tuple[int, int], list]) -> list[_Opcao]:
    res = []
    turnos = [at.turno_id] if at.turno_id else sorted({t for (u, t) in grade if u == at.unidade_id})
    for t in turnos:
        slots_turno = grade.get((at.unidade_id, t), [])
        for dia in at.dias_permitidos:
            seq = [s for s in slots_turno if dia in s.dias]
            for i in range(len(seq) - at.num_periodos + 1):
                bloco = seq[i:i + at.num_periodos]
                res.append(_Opcao(len(res), dia, bloco, bloco[0].ini, bloco[-1].fim,
                                  sum(s.fim - s.ini for s in bloco), t, at.unidade_id, any(s.excepcional for s in bloco)))
    return res


def _fases(atividades: list[AtividadeS], fixas) -> list[tuple[frozenset, frozenset]]:
    """Conjuntos maximais (atividades, fixas) simultaneamente ativos."""
    pontos = sorted({a.data_ini for a in atividades} | {a.data_fim + 1 for a in atividades}
                    | {f.data_ini for f in fixas} | {f.data_fim + 1 for f in fixas})
    chaves = set()
    for p in pontos:
        ats = frozenset(a.chave for a in atividades if a.data_ini <= p <= a.data_fim)
        if not ats:
            continue
        fx = frozenset(i for i, f in enumerate(fixas) if f.data_ini <= p <= f.data_fim)
        chaves.add((ats, fx))
    lista = list(chaves)
    maximais = [c for c in lista if not any(o != c and c[0] <= o[0] and c[1] <= o[1] for o in lista)]
    return maximais


def resolver(entrada: EntradaSolver) -> SaidaSolver:
    t0 = time.time()
    pesos = normalizar_pesos(entrada.pesos)
    diag: list[str] = []
    if not entrada.atividades:
        return SaidaSolver("SEM_DEMANDA", "Não há atividades pendentes no escopo selecionado.", 0.0)

    grade: dict[tuple[int, int], list] = defaultdict(list)
    for s in sorted(entrada.slots, key=lambda s: (s.unidade_id, s.turno_id, s.ordem)):
        grade[(s.unidade_id, s.turno_id)].append(s)
    instrutores = {i.id: i for i in entrada.instrutores}
    ambientes = {a.id: a for a in entrada.ambientes}
    ats = {a.chave: a for a in entrada.atividades}

    m = cp_model.CpModel()
    c: dict[tuple[str, int], cp_model.IntVar] = {}
    x: dict[tuple[str, int, int], cp_model.IntVar] = {}
    y: dict[tuple[str, int, int], cp_model.IntVar] = {}
    v: dict[tuple[str, int], cp_model.IntVar] = {}
    opcoes: dict[str, list[_Opcao]] = {}
    nao_alocaveis = []

    # ------------------------------------------------------------ opções e variáveis
    for a in entrada.atividades:
        ops_validas = []
        motivos = defaultdict(int)
        for o in _opcoes(a, grade):
            insts = [i for i in a.instrutores if i in instrutores and o.unidade_id in instrutores[i].unidades
                     and _contem(instrutores[i].disponibilidade, o.dia, o.ini, o.fim)]
            ambs = [r for r in a.ambientes if r in ambientes and
                    (not ambientes[r].disponibilidade or _contem(ambientes[r].disponibilidade, o.dia, o.ini, o.fim))]
            if not insts:
                motivos["sem instrutor habilitado disponível no horário"] += 1
                continue
            if not ambs:
                motivos["sem ambiente compatível disponível no horário"] += 1
                continue
            o.idx = len(ops_validas)
            ops_validas.append((o, insts, ambs))
        if not a.instrutores:
            motivos = {"nenhum instrutor habilitado cadastrado para a UC": 1}
        if not a.ambientes:
            motivos = {"nenhum ambiente tecnicamente compatível com a UC e a turma": 1}
        if len(ops_validas) < a.encontros:
            nao_alocaveis.append({"chave": a.chave, "descricao": a.descricao, "turma_uc_id": a.turma_uc_id, "grupo": a.grupo,
                                  "encontros": a.encontros, "opcoes_validas": len(ops_validas),
                                  "motivos": dict(motivos) or {"grade da turma sem períodos suficientes": 1}})
        opcoes[a.chave] = [o for o, _, _ in ops_validas]
        for i in {i for _, insts, _ in ops_validas for i in insts}:
            v[(a.chave, i)] = m.NewBoolVar(f"v_{a.chave}_{i}")
        for o, insts, ambs in ops_validas:
            cv = c[(a.chave, o.idx)] = m.NewBoolVar(f"c_{a.chave}_{o.idx}")
            xs = []
            for i in insts:
                xv = x[(a.chave, o.idx, i)] = m.NewBoolVar(f"x_{a.chave}_{o.idx}_{i}")
                m.AddImplication(xv, v[(a.chave, i)])
                xs.append(xv)
            m.Add(sum(xs) == cv)
            ys = []
            for r in ambs:
                ys.append(y.setdefault((a.chave, o.idx, r), m.NewBoolVar(f"y_{a.chave}_{o.idx}_{r}")))
            m.Add(sum(ys) == cv)

    if nao_alocaveis and entrada.modo == "completo":
        for n in nao_alocaveis:
            diag.append(f"{n['descricao'] or n['chave']}: {n['opcoes_validas']} opção(ões) viável(is) para {n['encontros']} encontro(s) — "
                        + "; ".join(f"{k} ({q})" for k, q in n["motivos"].items()))
        return SaidaSolver("INVIAVEL", "Problema comprovadamente inviável: há atividades sem opções de horário suficientes antes mesmo da busca.",
                           time.time() - t0, nao_alocados=nao_alocaveis, diagnosticos=diag)

    termos: dict[str, list] = defaultdict(list)  # critério -> [(coef, var)]
    nao_atendidos = {}
    for a in entrada.atividades:
        cs = [c[(a.chave, o.idx)] for o in opcoes[a.chave]]
        vs = [var for (k, _i), var in v.items() if k == a.chave]
        if entrada.modo == "completo":
            m.Add(sum(cs) == a.encontros)
            m.Add(sum(vs) == 1)
        else:
            m.Add(sum(cs) <= a.encontros)
            m.Add(sum(vs) <= 1)
            falta = m.NewIntVar(0, a.encontros, f"falta_{a.chave}")
            m.Add(falta == a.encontros - sum(cs))
            nao_atendidos[a.chave] = falta
            fator = 1 + (3 - a.prioridade) * 0.25
            termos["demanda_nao_atendida"].append((fator, falta))
            if a.urgencia > 0:
                termos["prazos"].append((a.urgencia, falta))

    # ------------------------------------------------------------ fases
    fixas = entrada.fixas
    fases = _fases(entrada.atividades, fixas)

    def restringir_pontos(itens, fixos, capacidade, nome):
        """itens: [(var, ini, fim, qtd)], fixos: [(ini, fim, qtd)]; garante soma ≤ capacidade em todo instante."""
        if not itens:
            return
        pontos = sorted({i[1] for i in itens} | {f[0] for f in fixos})
        for t in pontos:
            cobertos = [(var, q) for var, ini, fim, q in itens if ini <= t < fim]
            if not cobertos:
                continue
            fixo = sum(q for ini, fim, q in fixos if ini <= t < fim)
            if len(cobertos) == 1 and cobertos[0][1] + fixo <= capacidade:
                continue
            m.Add(sum(q * var for var, q in cobertos) <= capacidade - fixo)

    turma_grupos: dict[int, set[int]] = defaultdict(lambda: {1})
    for a in entrada.atividades:
        if a.grupo is not None:
            turma_grupos[a.turma_id].add(a.grupo)

    for ats_fase, fx_fase in fases:
        ativas = [ats[k] for k in ats_fase]
        fixas_fase = [fixas[i] for i in fx_fase]
        por_recurso: dict[tuple, list] = defaultdict(list)
        fixos_recurso: dict[tuple, list] = defaultdict(list)
        minutos_instr_dia: dict[tuple, list] = defaultdict(list)
        for a in ativas:
            for o in opcoes[a.chave]:
                cv = c[(a.chave, o.idx)]
                for g in turma_grupos[a.turma_id]:
                    if g in a.grupos:
                        por_recurso[("turma", a.turma_id, g, o.dia)].append((cv, o.ini, o.fim, 1))
                for i in a.instrutores:
                    xv = x.get((a.chave, o.idx, i))
                    if xv is not None:
                        por_recurso[("instrutor", i, o.dia)].append((xv, o.ini, o.fim, 1))
                        minutos_instr_dia[(i, o.dia)].append((o.minutos, xv))
                for r in a.ambientes:
                    yv = y.get((a.chave, o.idx, r))
                    if yv is not None:
                        prep = ambientes[r].preparacao_min
                        por_recurso[("ambiente", r, o.dia)].append((yv, o.ini, o.fim + prep, 1))
                        for tipo, q in a.recursos_moveis.get(str(r), {}).items():
                            por_recurso[("movel", f"{a.unidade_id}:{tipo}", o.dia)].append((yv, o.ini, o.fim, q))
        fixo_min_dia: dict[tuple, int] = defaultdict(int)
        for f in fixas_fase:
            if f.recurso == "turma":
                for g in turma_grupos[int(f.recurso_id)]:
                    if g in f.grupos:
                        fixos_recurso[("turma", int(f.recurso_id), g, f.dia)].append((f.ini, f.fim, 1))
            elif f.recurso == "instrutor":
                fixos_recurso[("instrutor", int(f.recurso_id), f.dia)].append((f.ini, f.fim, 1))
                fixo_min_dia[(int(f.recurso_id), f.dia)] += f.minutos
            elif f.recurso == "ambiente":
                fixos_recurso[("ambiente", int(f.recurso_id), f.dia)].append((f.ini, f.fim, 1))
            elif f.recurso == "recurso_movel":
                fixos_recurso[("movel", f.recurso_id, f.dia)].append((f.ini, f.fim, f.quantidade))
        for chave, itens in por_recurso.items():
            cap = entrada.acervo_movel.get(chave[1], 0) if chave[0] == "movel" else 1
            restringir_pontos(itens, fixos_recurso.get(chave, []), cap, chave)

        # limites diários / semanais de instrutores
        semana: dict[int, list] = defaultdict(list)
        for (i, dia), itens in minutos_instr_dia.items():
            inst = instrutores[i]
            fixo = fixo_min_dia.get((i, dia), 0)
            m.Add(sum(mn * xv for mn, xv in itens) <= max(inst.max_dia_min - fixo, 0))
            semana[i].extend(itens)
        for i, itens in semana.items():
            fixo = sum(mn for (ii, _d), mn in fixo_min_dia.items() if ii == i)
            m.Add(sum(mn * xv for mn, xv in itens) <= max(instrutores[i].limite_semanal_min - fixo, 0))

        # descanso entre jornadas (inclui domingo → segunda)
        for i, inst in instrutores.items():
            if inst.descanso_min <= 0:
                continue
            dias = defaultdict(list)
            for key, itens in por_recurso.items():
                if key[0] == "instrutor" and key[1] == i:
                    dias[key[2]].extend(itens)
            fixos_d = defaultdict(list)
            for key, itens in fixos_recurso.items():
                if key[0] == "instrutor" and key[1] == i:
                    fixos_d[key[2]].extend(itens)
            for d in range(7):
                d2 = (d + 1) % 7
                if not (dias[d] or fixos_d[d]) or not (dias[d2] or fixos_d[d2]):
                    continue
                if not dias[d] and not dias[d2]:
                    continue
                ult = m.NewIntVar(0, 1440, "")
                pri = m.NewIntVar(0, 1440, "")
                for xv, ini, fim, _q in dias[d]:
                    m.Add(ult >= fim).OnlyEnforceIf(xv)
                for ini, fim, _q in fixos_d[d]:
                    m.Add(ult >= fim)
                for xv, ini, fim, _q in dias[d2]:
                    m.Add(pri <= ini).OnlyEnforceIf(xv)
                for ini, fim, _q in fixos_d[d2]:
                    m.Add(pri <= ini)
                m.Add(ult - pri <= 1440 - inst.descanso_min)

        # deslocamento entre unidades (instrutores multiunidade)
        for i, inst in instrutores.items():
            if len(inst.unidades) < 2:
                continue
            for d in range(7):
                itens = []
                for a in ativas:
                    for o in opcoes[a.chave]:
                        xv = x.get((a.chave, o.idx, i))
                        if xv is not None and o.dia == d:
                            itens.append((xv, o.ini, o.fim, o.unidade_id))
                fixos_u = [(None, f.ini, f.fim, f.unidade_id) for f in fixas_fase
                           if f.recurso == "instrutor" and int(f.recurso_id) == i and f.dia == d]
                todos = itens + fixos_u
                for p1 in range(len(todos)):
                    for p2 in range(p1 + 1, len(todos)):
                        a1, a2 = todos[p1], todos[p2]
                        if a1[0] is None and a2[0] is None or a1[3] == a2[3]:
                            continue
                        desl = entrada.deslocamentos.get(f"{min(a1[3], a2[3])}:{max(a1[3], a2[3])}", 60)
                        folga = a2[1] - a1[2] if a1[2] <= a2[1] else a1[1] - a2[2]
                        if folga < desl:
                            vars_ = [z for z in (a1[0], a2[0]) if z is not None]
                            m.AddBoolOr([z.Not() for z in vars_])

    # ------------------------------------------------------------ objetivo
    dicas: set = set()
    for a in entrada.atividades:
        for o in opcoes[a.chave]:
            cv = c[(a.chave, o.idx)]
            if o.excepcional:
                termos["horarios_excepcionais"].append((1, cv))
            for r in a.ambientes:
                yv = y.get((a.chave, o.idx, r))
                if yv is None:
                    continue
                amb = ambientes[r]
                ocioso = max(0, round(100 * (amb.capacidade_operacional - a.tamanho) / amb.capacidade_operacional))
                if ocioso:
                    termos["ocupacao_inadequada"].append((ocioso, yv))
                if amb.especializado and a.aceita_convencional:
                    termos["especializado_desnecessario"].append((1, yv))
            for i in a.instrutores:
                xv = x.get((a.chave, o.idx, i))
                if xv is not None and instrutores[i].turno_preferencial_id and instrutores[i].turno_preferencial_id != o.turno_id:
                    termos["preferencia_turno"].append((1, xv))
        # concentração no mesmo dia
        if pesos["concentracao_dias"] > 0 and a.encontros > 1:
            por_dia = defaultdict(list)
            for o in opcoes[a.chave]:
                por_dia[o.dia].append(c[(a.chave, o.idx)])
            for dia, cs in por_dia.items():
                if len(cs) > 1:
                    exc = m.NewIntVar(0, a.encontros, "")
                    m.Add(exc >= sum(cs) - 1)
                    termos["concentracao_dias"].append((1, exc))
        # mudanças em relação ao padrão vigente / aprovado
        for lista, criterio in ((a.anteriores, "mudancas_vigente"), (a.preservar, "preservar_aprovados")):
            if not lista or pesos[criterio] <= 0:
                continue
            mantidos = []
            for ant in lista:
                o = next((o for o in opcoes[a.chave] if o.dia == ant.dia and o.slots[0].id == ant.slot_inicio_id), None)
                if o is None:
                    continue
                same = m.NewBoolVar("")
                m.AddImplication(same, c[(a.chave, o.idx)])
                if ant.instrutor_id is not None:
                    xv = x.get((a.chave, o.idx, ant.instrutor_id))
                    if xv is None:
                        m.Add(same == 0)
                    else:
                        m.AddImplication(same, xv)
                if ant.ambiente_id is not None:
                    yv = y.get((a.chave, o.idx, ant.ambiente_id))
                    if yv is None:
                        m.Add(same == 0)
                    else:
                        m.AddImplication(same, yv)
                mantidos.append(same)
                dicas.add((a.chave, o.idx))
            alterados = m.NewIntVar(0, len(lista), "")
            m.Add(alterados == len(lista) - sum(mantidos))
            termos[criterio].append((1, alterados))

    # equilíbrio de carga (maior ocupação percentual)
    if pesos["equilibrio_carga"] > 0:
        lmax = m.NewIntVar(0, 1000, "lmax")
        carga = defaultdict(list)
        for (k, oi, i), xv in x.items():
            carga[i].append((opcoes[k][oi].minutos, xv))
        fixo_sem = defaultdict(int)
        for f in fixas:
            if f.recurso == "instrutor":
                fixo_sem[int(f.recurso_id)] += f.minutos
        for i, itens in carga.items():
            lim = max(instrutores[i].limite_semanal_min, 1)
            # 100 * minutos / limite <= lmax  →  100*minutos <= lmax*limite
            m.Add(100 * (sum(mn * xv for mn, xv in itens) + fixo_sem[i]) <= lmax * lim)
        termos["equilibrio_carga"].append((1, lmax))

    # janelas (instrutores e turmas) e aulas isoladas
    def janelas(itens_por_dia_slot, criterio, fixos_por_dia_slot):
        """gap[p] = 1 se o período p está vago, mas há aula antes e depois no mesmo turno."""
        zero, um = m.NewConstant(0), m.NewConstant(1)
        for (dia, unidade, turno), slot_ids in itens_por_dia_slot["grade"].items():
            occ, variavel = [], False
            for sid in slot_ids:
                vars_ = itens_por_dia_slot["vars"].get((dia, sid), [])
                if (dia, sid) in fixos_por_dia_slot:
                    occ.append(um)
                elif vars_:
                    ob = m.NewBoolVar("")
                    for z in vars_:
                        m.AddImplication(z, ob)
                    m.Add(ob <= sum(vars_))
                    occ.append(ob)
                    variavel = True
                else:
                    occ.append(zero)
            n = len(occ)
            if not variavel or n < 3:
                continue
            antes, depois = [zero] * n, [zero] * n
            for p in range(1, n):
                antes[p] = m.NewBoolVar("")
                m.AddMaxEquality(antes[p], [antes[p - 1], occ[p - 1]])
            for p in range(n - 2, -1, -1):
                depois[p] = m.NewBoolVar("")
                m.AddMaxEquality(depois[p], [depois[p + 1], occ[p + 1]])
            for p in range(1, n - 1):
                gap = m.NewBoolVar("")
                m.Add(gap >= antes[p] + depois[p] - occ[p] - 1)
                termos[criterio].append((1, gap))

    if pesos["janelas_instrutores"] > 0 or pesos["janelas_turmas"] > 0 or pesos["aulas_isoladas"] > 0:
        slot_por_id = {s.id: s for s in entrada.slots}
        inst_map = defaultdict(lambda: {"grade": defaultdict(list), "vars": defaultdict(list)})
        turma_map = defaultdict(lambda: {"grade": defaultdict(list), "vars": defaultdict(list)})
        turma_dia_periodos = defaultdict(list)
        for a in entrada.atividades:
            for o in opcoes[a.chave]:
                cv = c[(a.chave, o.idx)]
                if a.grupo is None:
                    for s in o.slots:
                        turma_map[a.turma_id]["vars"][(o.dia, s.id)].append(cv)
                    turma_dia_periodos[(a.turma_id, o.dia)].append((len(o.slots), cv))
                for i in a.instrutores:
                    xv = x.get((a.chave, o.idx, i))
                    if xv is not None:
                        for s in o.slots:
                            inst_map[i]["vars"][(o.dia, s.id)].append(xv)
        for mp in (inst_map, turma_map):
            for rid, info in mp.items():
                chaves = {(d, slot_por_id[sid].unidade_id, slot_por_id[sid].turno_id) for (d, sid) in info["vars"]}
                for d, u, t in chaves:
                    info["grade"][(d, u, t)] = [s.id for s in grade[(u, t)] if d in s.dias]
        fixos_inst = defaultdict(set)
        fixos_turma = defaultdict(set)
        for f in fixas:
            for s in entrada.slots:
                if f.dia in s.dias and s.ini < f.fim and f.ini < s.fim:
                    if f.recurso == "instrutor":
                        fixos_inst[int(f.recurso_id)].add((f.dia, s.id))
                    elif f.recurso == "turma" and len(f.grupos) > 1:
                        fixos_turma[int(f.recurso_id)].add((f.dia, s.id))
        if pesos["janelas_instrutores"] > 0:
            for i, info in inst_map.items():
                janelas(info, "janelas_instrutores", fixos_inst[i])
        if pesos["janelas_turmas"] > 0:
            for t, info in turma_map.items():
                janelas(info, "janelas_turmas", fixos_turma[t])
        minp = int(pesos.get("min_periodos_dia", 2))
        if pesos["aulas_isoladas"] > 0 and minp > 1:
            for (t, d), itens in turma_dia_periodos.items():
                has = m.NewBoolVar("")
                for _n, cv in itens:
                    m.AddImplication(cv, has)
                curto = m.NewBoolVar("")
                m.Add(minp * curto >= minp * has - sum(n * cv for n, cv in itens))
                termos["aulas_isoladas"].append((1, curto))

    # deslocamentos (dias com aulas em mais de uma unidade)
    if pesos["deslocamentos"] > 0:
        for i, inst in instrutores.items():
            if len(inst.unidades) < 2:
                continue
            por_dia_un = defaultdict(list)
            for (k, oi, ii), xv in x.items():
                if ii == i:
                    o = opcoes[k][oi]
                    por_dia_un[(o.dia, o.unidade_id)].append(xv)
            for d in range(7):
                ws = []
                for (dd, u), xs in por_dia_un.items():
                    if dd != d:
                        continue
                    w = m.NewBoolVar("")
                    for xv in xs:
                        m.AddImplication(xv, w)
                    ws.append(w)
                if len(ws) > 1:
                    viag = m.NewIntVar(0, len(ws), "")
                    m.Add(viag >= sum(ws) - 1)
                    termos["deslocamentos"].append((1, viag))

    objetivo = []
    for crit, itens in termos.items():
        w = pesos.get(crit, 0)
        if w <= 0:
            continue
        for coef, var in itens:
            k = round(w * coef * ESCALA)
            if k:
                objetivo.append(k * var)
    if objetivo:
        m.Minimize(sum(objetivo))
    for chave in dicas:
        m.AddHint(c[chave], 1)

    # ------------------------------------------------------------ busca
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(entrada.limite_tempo_s)
    solver.parameters.num_workers = max(1, int(entrada.threads))
    solver.parameters.random_seed = int(entrada.semente)
    st = solver.Solve(m)
    tempo = time.time() - t0
    stats = {"variaveis": len(m.Proto().variables), "restricoes": len(m.Proto().constraints),
             "conflitos": solver.NumConflicts(), "ramificacoes": solver.NumBranches(), "fases": len(fases),
             "tempo_busca_s": solver.WallTime()}

    if st == cp_model.INFEASIBLE:
        return SaidaSolver("INVIAVEL", "O solver provou que não existe grade que respeite todas as restrições obrigatórias "
                           "para toda a demanda selecionada.", tempo, diagnosticos=diag, estatisticas=stats, nao_alocados=nao_alocaveis)
    if st == cp_model.MODEL_INVALID:
        return SaidaSolver("MODELO_INVALIDO", m.Validate() or "Modelo inválido.", tempo, estatisticas=stats)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SaidaSolver("SEM_SOLUCAO_NO_LIMITE",
                           f"Nenhuma solução encontrada em {entrada.limite_tempo_s:.0f} s. Isso NÃO prova inviabilidade: "
                           "aumente o limite de tempo, reduza o escopo ou use o modo parcial.", tempo, estatisticas=stats)

    atribs: list[Atribuicao] = []
    nao_alocados = list(nao_alocaveis)
    for a in entrada.atividades:
        enc = 0
        for o in opcoes[a.chave]:
            if solver.Value(c[(a.chave, o.idx)]):
                inst = next((i for i in a.instrutores if (a.chave, o.idx, i) in x and solver.Value(x[(a.chave, o.idx, i)])), None)
                amb = next((r for r in a.ambientes if (a.chave, o.idx, r) in y and solver.Value(y[(a.chave, o.idx, r)])), None)
                atribs.append(Atribuicao(a.chave, enc, o.dia, o.slots[0].id, [s.id for s in o.slots], len(o.slots),
                                         o.ini, o.fim, o.minutos, inst, amb))
                enc += 1
        if a.chave in nao_atendidos and solver.Value(nao_atendidos[a.chave]) > 0 and not any(n["chave"] == a.chave for n in nao_alocados):
            nao_alocados.append({"chave": a.chave, "descricao": a.descricao, "turma_uc_id": a.turma_uc_id, "grupo": a.grupo,
                                 "encontros": a.encontros, "alocados": enc,
                                 "motivos": {"conflito com outras atividades ou limites de recursos no horário disponível": 1}})
    valores = {}
    for crit, itens in termos.items():
        valores[crit] = float(sum(coef * solver.Value(var) for coef, var in itens))
    status = "OTIMA" if st == cp_model.OPTIMAL else "VIAVEL"
    motivo = ("Solução comprovadamente ótima para a função objetivo configurada." if status == "OTIMA"
              else f"Solução viável encontrada; o limite de tempo ({entrada.limite_tempo_s:.0f} s) foi atingido antes de provar a otimalidade.")
    if nao_alocados:
        motivo += f" {len(nao_alocados)} atividade(s) com encontros não alocados (modo parcial)."
    return SaidaSolver(status, motivo, tempo, objetivo=solver.ObjectiveValue() / ESCALA if objetivo else 0.0,
                       limite_inferior=solver.BestObjectiveBound() / ESCALA if objetivo else 0.0,
                       atribuicoes=atribs, nao_alocados=nao_alocados, termos=valores, diagnosticos=diag, estatisticas=stats)
