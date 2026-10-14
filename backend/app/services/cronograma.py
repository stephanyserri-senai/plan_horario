"""Cronograma (Gantt) com caminho crítico: área → curso → turma → unidade curricular.

Para cada turma×UC:
- início/fim vêm das aulas gravadas no cenário; se ainda falta carga horária sem
  horário, o fim é PROJETADO pelo ritmo semanal da UC (encontros × aulas);
- folga = dias entre o fim (real ou projetado) e o prazo (data-limite da UC ou fim da turma);
- crítica = atrasada (fim após o prazo) ou folga abaixo do limiar.

Caminho crítico de uma turma: a sequência de UCs que determina a data de término
da turma — parte da UC que termina por último e segue pelos pré-requisitos
cadastrados (o pré-requisito que termina mais tarde). Sem pré-requisitos, é a UC
(ou as UCs empatadas) que termina por último.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alocacao, Area, Curso, Instrutor, Turma, TurmaUC, UCPrerequisito, UnidadeCurricular
from app.services.planejamento import situacao_carga_horaria

LIMIAR_FOLGA_DIAS = 7


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def cronograma(db: Session, cenario_id: int, unidade_id: int | None = None, area_id: int | None = None, curso_id: int | None = None,
               unidades_permitidas=None, hoje: date | None = None, limiar_folga: int = LIMIAR_FOLGA_DIAS) -> dict:
    hoje = hoje or date.today()
    q = (select(TurmaUC, Turma, Curso).join(Turma, Turma.id == TurmaUC.turma_id).join(Curso, Curso.id == Turma.curso_id)
         .where(TurmaUC.ativo.is_(True), Turma.ativo.is_(True), Turma.simulacao_id.is_(None),
                TurmaUC.situacao != "cancelada", Turma.situacao != "cancelada"))
    if unidade_id:
        q = q.where(Turma.unidade_id == unidade_id)
    if unidades_permitidas is not None:
        q = q.where(Turma.unidade_id.in_(unidades_permitidas))
    if area_id:
        q = q.where(func.coalesce(Turma.area_id, Curso.area_id) == area_id)
    if curso_id:
        q = q.where(Turma.curso_id == curso_id)
    linhas = db.execute(q.order_by(Turma.codigo, TurmaUC.id)).all()
    tuc_ids = [t.id for t, _, _ in linhas]

    # datas das aulas por turma×UC (uma consulta)
    datas = {r[0]: (r[1], r[2]) for r in db.execute(
        select(Alocacao.turma_uc_id, func.min(Alocacao.data), func.max(Alocacao.data))
        .where(Alocacao.cenario_id == cenario_id, Alocacao.status != "cancelada", Alocacao.turma_uc_id.in_(tuc_ids or [-1]))
        .group_by(Alocacao.turma_uc_id))}
    instrutores = defaultdict(set)
    for tuc_id, nome in db.execute(select(Alocacao.turma_uc_id, Instrutor.nome).join(Instrutor, Instrutor.id == Alocacao.instrutor_id)
                                   .where(Alocacao.cenario_id == cenario_id, Alocacao.turma_uc_id.in_(tuc_ids or [-1])).distinct()):
        instrutores[tuc_id].add(nome)
    prereq = defaultdict(set)
    for uc_id, pre_id in db.execute(select(UCPrerequisito.uc_id, UCPrerequisito.prerequisito_id)):
        prereq[uc_id].add(pre_id)
    areas = {a.id: a for a in db.scalars(select(Area))}
    ucs = {u.id: u for u in db.scalars(select(UnidadeCurricular).where(UnidadeCurricular.id.in_({t.uc_id for t, _, _ in linhas} or {-1})))}

    itens_uc = []
    for tuc, turma, curso in linhas:
        uc = ucs[tuc.uc_id]
        info = situacao_carga_horaria(db, cenario_id, tuc)
        primeira, ultima = datas.get(tuc.id, (None, None))
        inicio_previsto = tuc.data_inicio or turma.data_inicio
        limite = date.fromisoformat(info["data_limite"])
        restante = info["restante_h"]
        ritmo_semana_h = max(info["horas_por_encontro"] * max(uc.encontros_semanais, 1), 0.1)
        sem_horario = restante > 0.01
        if sem_horario:
            base = max(ultima or (inicio_previsto - timedelta(days=1)), hoje - timedelta(days=1))
            fim = base + timedelta(days=7 * math.ceil(restante / ritmo_semana_h))
        else:
            fim = ultima or inicio_previsto
        inicio = primeira or max(inicio_previsto, hoje)
        folga = (limite - fim).days
        area = areas.get(turma.area_id or curso.area_id)
        itens_uc.append({
            "id": f"u:{tuc.id}", "tipo": "uc", "pai": f"t:{turma.id}", "turma_id": turma.id, "uc_id": uc.id, "codigo": uc.codigo, "nome": uc.nome,
            "inicio": _iso(inicio), "fim": _iso(fim), "ultima_aula": _iso(ultima), "limite": _iso(limite),
            "total_h": info["total_h"], "realizada_h": info["realizada_h"], "programada_h": info["programada_h"], "restante_h": restante,
            "sem_horario": sem_horario, "folga_dias": folga, "atrasado": fim > limite, "critico": fim > limite or folga <= limiar_folga,
            "caminho_critico": False, "instrutores": sorted(instrutores.get(tuc.id, [])), "depende_de": [],
            "_area": area, "_curso": curso, "_turma": turma,
        })

    # caminho crítico por turma
    por_turma = defaultdict(list)
    for it in itens_uc:
        por_turma[it["turma_id"]].append(it)
    for lst in por_turma.values():
        por_uc = {it["uc_id"]: it for it in lst}
        for it in lst:
            it["depende_de"] = [por_uc[p]["id"] for p in prereq.get(it["uc_id"], ()) if p in por_uc]
        fim_max = max(it["fim"] for it in lst)
        fila = [it for it in lst if it["fim"] == fim_max]
        vistos = set()
        while fila:
            it = fila.pop()
            if it["id"] in vistos:
                continue
            vistos.add(it["id"])
            it["caminho_critico"] = True
            pres = [por_uc[p] for p in prereq.get(it["uc_id"], ()) if p in por_uc]
            if pres:
                fila.append(max(pres, key=lambda x: x["fim"]))

    # agregados: turma, curso, área
    grupos: dict[str, dict] = {}

    def acumular(gid, tipo, pai, codigo, nome, it, limite=None):
        g = grupos.get(gid)
        if g is None:
            g = grupos[gid] = {"id": gid, "tipo": tipo, "pai": pai, "codigo": codigo, "nome": nome, "inicio": it["inicio"], "fim": it["fim"],
                               "limite": limite, "total_h": 0.0, "realizada_h": 0.0, "programada_h": 0.0, "restante_h": 0.0,
                               "ucs": 0, "ucs_criticas": 0, "ucs_atrasadas": 0, "sem_horario": False}
        g["inicio"] = min(g["inicio"], it["inicio"])
        g["fim"] = max(g["fim"], it["fim"])
        for k in ("total_h", "realizada_h", "programada_h", "restante_h"):
            g[k] = round(g[k] + it[k], 2)
        g["ucs"] += 1
        g["ucs_criticas"] += int(it["critico"])
        g["ucs_atrasadas"] += int(it["atrasado"])
        g["sem_horario"] = g["sem_horario"] or it["sem_horario"]

    for it in itens_uc:
        area, curso, turma = it.pop("_area"), it.pop("_curso"), it.pop("_turma")
        aid = f"a:{area.id}" if area else "a:0"
        acumular(aid, "area", None, area.codigo if area else "", area.nome if area else "Sem área definida", it)
        acumular(f"c:{curso.id}", "curso", aid, curso.codigo, curso.nome, it)
        acumular(f"t:{turma.id}", "turma", f"c:{curso.id}", turma.codigo, turma.nome, it, turma.data_fim.isoformat())
    for g in grupos.values():
        if g["limite"]:
            g["folga_dias"] = (date.fromisoformat(g["limite"]) - date.fromisoformat(g["fim"])).days
            g["atrasado"] = g["folga_dias"] < 0
            g["critico"] = g["atrasado"] or g["folga_dias"] <= limiar_folga
        else:
            g["critico"] = g["ucs_criticas"] > 0
            g["atrasado"] = g["ucs_atrasadas"] > 0

    turmas = [g for g in grupos.values() if g["tipo"] == "turma"]
    return {
        "hoje": hoje.isoformat(), "limiar_folga_dias": limiar_folga,
        "itens": sorted(grupos.values(), key=lambda g: ({"area": 0, "curso": 1, "turma": 2}[g["tipo"]], g["nome"])) + itens_uc,
        "resumo": {
            "turmas": len(turmas), "turmas_atrasadas": sum(1 for t in turmas if t["atrasado"]),
            "turmas_em_risco": sum(1 for t in turmas if t["critico"] and not t["atrasado"]),
            "ucs": len(itens_uc), "ucs_criticas": sum(1 for i in itens_uc if i["critico"]),
            "ucs_sem_horario": sum(1 for i in itens_uc if i["sem_horario"]),
            "inicio": min((i["inicio"] for i in itens_uc), default=None), "fim": max((i["fim"] for i in itens_uc), default=None),
        },
        "explicacao": ("Barras mostram o período de cada unidade curricular conforme as aulas gravadas; a parte tracejada é a projeção do que "
                       "ainda não tem horário, no ritmo semanal da UC. Crítica = termina depois do prazo ou com folga de até "
                       f"{limiar_folga} dias. Caminho crítico = sequência de UCs que define a data de término da turma."),
    }
