"""Índice de aderência do instrutor aos cursos da(s) área(s) dele e propostas de PDI.

- Aderência a um curso = parte da carga horária das UCs técnicas do curso que o instrutor pode ministrar:
  "sim" vale 100% da UC, "em partes" vale 50%, e quem tem a competência mas não a certificação exigida
  (ex.: NR-10) ainda não pode dar a UC, então ela conta 0 até a certificação. UCs transversais ficam de fora
  (qualquer instrutor pode dar). As versões da matriz (por tipo de oferta) se juntam pelo código da UC.
- Aderência à área = o mesmo cálculo somando todos os cursos da área; geral = todas as áreas do instrutor
  (principal e outras; quem "atende todas as áreas" entra nas áreas onde já tem UC marcada).
- PDI: cada UC que falta vira uma proposta (aprender, completar ou certificar), com ganho no curso e na área,
  demanda (turmas ativas do curso) e quantos outros instrutores já dão a UC; a prioridade junta os três.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (Area, CompetenciaInstrutor, Curso, HabilitacaoInstrutor, Instrutor, InstrutorArea, MatrizCurricular, PdiItem,
                        Turma, TurmaUC, UnidadeCurricular)

PESO = {"pleno": 1.0, "parcial": 0.5}
ROTULO = {"sim": "Ministra", "em_partes": "Em partes", "sem_certificacao": "Falta certificação", "nao": "Não ministra"}
PRAZO_MESES = {"alta": 3, "media": 6, "baixa": 12}


def _pct(feito: float, total: float) -> float:
    return round(100 * feito / total, 1) if total else 0.0


class Base:
    """Catálogo carregado uma vez: cursos com as UCs técnicas (por código), competências, certificações e demanda."""

    def __init__(self, db: Session, hoje: date | None = None):
        self.db, self.hoje = db, hoje or date.today()
        self.areas = {a.id: a for a in db.scalars(select(Area))}
        self.cursos = {c.id: c for c in db.scalars(select(Curso).where(Curso.ativo.is_(True)))}
        # curso → código da UC → {nome, ch, ids, cert}
        self.ucs: dict[int, dict[str, dict]] = defaultdict(dict)
        self.transversais: dict[int, int] = defaultdict(int)
        q = (select(UnidadeCurricular, MatrizCurricular.curso_id).join(MatrizCurricular, MatrizCurricular.id == UnidadeCurricular.matriz_id)
             .where(MatrizCurricular.ativo.is_(True), MatrizCurricular.situacao != "encerrada", UnidadeCurricular.ativo.is_(True)))
        for uc, cid in self.db.execute(q):
            if cid not in self.cursos:
                continue
            if uc.categoria == "transversal":
                self.transversais[cid] += 1
                continue
            u = self.ucs[cid].setdefault(uc.codigo, {"codigo": uc.codigo, "nome": uc.nome, "ch": 0, "ids": set(), "cert": None})
            u["ch"] = max(u["ch"], uc.carga_horaria_total or 0)
            u["ids"].add(uc.id)
            u["cert"] = u["cert"] or (uc.certificacao_exigida or "").strip() or None
        self.uc_curso = {i: cid for cid, us in self.ucs.items() for u in us.values() for i in u["ids"]}
        # instrutor → uc_id → peso (competência ativa e válida)
        self.comp: dict[int, dict[int, float]] = defaultdict(dict)
        for c in db.scalars(select(CompetenciaInstrutor).where(CompetenciaInstrutor.ativo.is_(True), CompetenciaInstrutor.nivel.in_(list(PESO)))):
            if c.valido_ate and c.valido_ate < self.hoje:
                continue
            self.comp[c.instrutor_id][c.uc_id] = max(self.comp[c.instrutor_id].get(c.uc_id, 0), PESO[c.nivel])
        self.certs: dict[int, set[str]] = defaultdict(set)
        for h in db.scalars(select(HabilitacaoInstrutor).where(HabilitacaoInstrutor.ativo.is_(True))):
            if not h.valido_ate or h.valido_ate >= self.hoje:
                self.certs[h.instrutor_id].add(h.nome.strip().lower())
        self.extras: dict[int, set[int]] = defaultdict(set)
        for ia in db.scalars(select(InstrutorArea)):
            self.extras[ia.instrutor_id].add(ia.area_id)
        # demanda: turmas ativas por curso que têm a UC (código) na oferta
        self.demanda: dict[tuple[int, str], int] = defaultdict(int)
        q = (select(Turma.curso_id, UnidadeCurricular.codigo, func.count(func.distinct(Turma.id)))
             .join(TurmaUC, TurmaUC.turma_id == Turma.id).join(UnidadeCurricular, UnidadeCurricular.id == TurmaUC.uc_id)
             .where(Turma.ativo.is_(True), Turma.situacao.notin_(["concluida", "cancelada"]), Turma.simulacao_id.is_(None))
             .group_by(Turma.curso_id, UnidadeCurricular.codigo))
        for cid, cod, n in db.execute(q):
            self.demanda[(cid, cod)] = n
        self.ativos = {i.id: i for i in db.scalars(select(Instrutor).where(Instrutor.ativo.is_(True)))}
        self.nivel_curso = self._niveis()

    def _niveis(self) -> dict[int, str]:
        """Nível que o curso exige do instrutor, pela regra das turmas: oferta básica (AIB, qualificação) aceita o instrutor
        básico; só técnica (HTC, AIT...) exige técnico. Usa as versões da matriz, as turmas ativas e o tipo do curso."""
        from app.services.planejamento import OFERTAS_BASICAS, OFERTAS_TECNICAS, _sem_acento
        ofertas: dict[int, set[str]] = defaultdict(set)
        for cid, t in self.db.execute(select(MatrizCurricular.curso_id, MatrizCurricular.tipo_oferta).where(MatrizCurricular.ativo.is_(True))):
            if t:
                ofertas[cid].add(t.strip().upper())
        for cid, cod in self.db.execute(select(Turma.curso_id, Turma.codigo).where(Turma.ativo.is_(True), Turma.simulacao_id.is_(None))):
            ofertas[cid].add((cod or "").split("-")[0].strip().upper())
        res = {}
        for cid, c in self.cursos.items():
            o = ofertas.get(cid, set())
            if o & OFERTAS_BASICAS:
                res[cid] = "basico"
            elif o & OFERTAS_TECNICAS:
                res[cid] = "tecnico"
            else:
                tipo = _sem_acento(c.tipo or "")
                res[cid] = "basico" if ("qualifica" in tipo or "basic" in tipo) else "tecnico"
        return res

    def no_nivel(self, inst: Instrutor, cid: int) -> bool:
        """Instrutor básico só entra nos cursos de nível básico (regra de nível, sem exceção)."""
        return (inst.nivel or "tecnico") != "basico" or self.nivel_curso.get(cid) == "basico"

    def situacao(self, iid: int, u: dict) -> tuple[str, float]:
        """Situação do instrutor numa UC (por código no curso) e quanto ela vale (0 a 1)."""
        peso = max((self.comp[iid].get(i, 0) for i in u["ids"]), default=0)
        if peso and u["cert"] and u["cert"].lower() not in self.certs[iid]:
            return "sem_certificacao", 0.0
        return ("sim" if peso >= 1 else "em_partes" if peso else "nao"), peso

    def habilitados(self, u: dict, exceto: int, cid: int | None = None) -> int:
        """Outros instrutores ativos que já podem dar a UC (com a certificação, se exigida, e no nível do curso)."""
        n = 0
        for iid, inst in self.ativos.items():
            if iid != exceto and (cid is None or self.no_nivel(inst, cid)) and self.situacao(iid, u)[0] in ("sim", "em_partes"):
                n += 1
        return n

    def nomes_habilitados(self, u: dict, cid: int | None = None) -> list[str]:
        return sorted(inst.nome for iid, inst in self.ativos.items()
                      if (cid is None or self.no_nivel(inst, cid)) and self.situacao(iid, u)[0] in ("sim", "em_partes"))

    def areas_do(self, inst: Instrutor) -> list[int]:
        areas = ([inst.area_id] if inst.area_id else []) + sorted(self.extras[inst.id] - {inst.area_id})
        if inst.todas_areas or not areas:  # atende todas: entra nas áreas onde já tem UC marcada
            marcadas = {self.cursos[self.uc_curso[i]].area_id for i in self.comp[inst.id] if i in self.uc_curso}
            areas += sorted(a for a in marcadas if a and a not in areas)
        return [a for a in areas if a in self.areas]


def _curso(base: Base, inst: Instrutor, cid: int) -> dict:
    c = base.cursos[cid]
    ucs, feito, total = [], 0.0, 0
    for u in sorted(base.ucs[cid].values(), key=lambda x: x["codigo"]):
        sit, peso = base.situacao(inst.id, u)
        marcado = max((base.comp[inst.id].get(i, 0) for i in u["ids"]), default=0)
        ucs.append({"codigo": u["codigo"], "nome": u["nome"], "ch": u["ch"], "situacao": sit, "rotulo": ROTULO[sit], "certificacao": u["cert"],
                    "marcado": "pleno" if marcado >= 1 else "parcial" if marcado else None})
        feito += peso * u["ch"]
        total += u["ch"]
    return {"curso_id": cid, "codigo": c.codigo, "nome": c.nome, "pct": _pct(feito, total), "ch_total": total, "ch_apta": round(feito, 1),
            "ucs_total": len(ucs), "ucs_sim": sum(1 for u in ucs if u["situacao"] == "sim"),
            "ucs_em_partes": sum(1 for u in ucs if u["situacao"] == "em_partes"),
            "ucs_faltam": sum(1 for u in ucs if u["situacao"] in ("nao", "sem_certificacao")),
            "transversais": base.transversais.get(cid, 0), "ucs": ucs}


def indice(db: Session, instrutor_id: int, base: Base | None = None, detalhe: bool = True) -> dict:
    """Aderência do instrutor: por curso, por área e geral."""
    base = base or Base(db)
    inst = db.get(Instrutor, instrutor_id)
    areas = []
    feito_g = total_g = 0.0
    for aid in base.areas_do(inst):
        da_area = [cid for cid in sorted(base.cursos, key=lambda x: base.cursos[x].nome) if base.cursos[cid].area_id == aid and base.ucs.get(cid)]
        cursos = [_curso(base, inst, cid) for cid in da_area if base.no_nivel(inst, cid)]
        fora = [base.cursos[cid].codigo for cid in da_area if not base.no_nivel(inst, cid)]
        feito = sum(c["ch_apta"] for c in cursos)
        total = sum(c["ch_total"] for c in cursos)
        feito_g, total_g = feito_g + feito, total_g + total
        if not detalhe:
            for c in cursos:
                c.pop("ucs")
        areas.append({"area_id": aid, "area": base.areas[aid].nome, "principal": aid == inst.area_id, "pct": _pct(feito, total),
                      "cursos_100": sum(1 for c in cursos if c["pct"] >= 99.95), "cursos": cursos, "fora_do_nivel": fora})
    return {"instrutor_id": inst.id, "nome": inst.nome, "geral": _pct(feito_g, total_g), "areas": areas, "multiarea": len(areas) > 1,
            "nivel": inst.nivel,
            "metodo": "Parte da carga horária das UCs técnicas que o instrutor pode ministrar: 'sim' vale a UC inteira, 'em partes' metade; "
                      "sem a certificação exigida a UC ainda não conta. UCs transversais ficam de fora (qualquer instrutor pode dar). "
                      "Instrutor básico entra só nos cursos de nível básico (AIB e qualificações)."}


def _prioridade(demanda: int, outros: int, ganho_curso: float, pct_curso: float, tipo: str) -> tuple[str, float]:
    """Demanda (turmas ativas), escassez (quantos outros dão a UC), ganho no curso e proximidade dos 100%."""
    pontos = min(demanda, 3) * 1.2 + (3 if outros == 0 else 1.5 if outros == 1 else 0) + min(ganho_curso, 40) / 10 + (1.5 if pct_curso >= 70 else 0)
    if tipo == "certificacao":
        pontos += 1  # destrava uma UC que o instrutor já sabe
    return ("alta" if pontos >= 7 else "media" if pontos >= 4 else "baixa"), round(pontos, 1)


def propostas(db: Session, instrutor_id: int, base: Base | None = None) -> dict:
    """Propostas de PDI: o que falta para o instrutor chegar a 100% nos cursos da(s) área(s), em ordem de prioridade."""
    base = base or Base(db)
    inst = db.get(Instrutor, instrutor_id)
    ind = indice(db, instrutor_id, base)
    ja = {(p.curso_id, p.uc_codigo, p.tipo) for p in db.scalars(select(PdiItem).where(PdiItem.instrutor_id == inst.id,
                                                                                      PdiItem.situacao.in_(["planejado", "em_andamento"])))}
    itens = []
    for a in ind["areas"]:
        ch_area = sum(c["ch_total"] for c in a["cursos"]) or 1
        for c in a["cursos"]:
            for u in c["ucs"]:
                if u["situacao"] == "sim":
                    continue
                uc = base.ucs[c["curso_id"]][u["codigo"]]
                tipo = {"nao": "uc", "em_partes": "completar", "sem_certificacao": "certificacao"}[u["situacao"]]
                falta = 0.5 if tipo == "completar" else 1.0
                ganho_c = round(100 * falta * u["ch"] / (c["ch_total"] or 1), 1)
                demanda = base.demanda.get((c["curso_id"], u["codigo"]), 0)
                outros = base.habilitados(uc, inst.id, c["curso_id"])
                prio, pontos = _prioridade(demanda, outros, ganho_c, c["pct"], tipo)
                acao = {"uc": f"Capacitar em {u['codigo']} – {u['nome']}",
                        "completar": f"Completar {u['codigo']} – {u['nome']} (hoje 'em partes')",
                        "certificacao": f"Obter a certificação {u['certificacao']} (já marcado em {u['codigo']})"}[tipo]
                porque = []
                if demanda:
                    porque.append(f"{demanda} turma(s) ativa(s) do curso têm a UC")
                porque.append("ninguém mais dá a UC" if outros == 0 else "só 1 outro instrutor dá a UC" if outros == 1 else f"{outros} outros instrutores dão a UC")
                if c["pct"] >= 70:
                    porque.append(f"aproxima {c['codigo']} de 100%")
                itens.append({"area_id": a["area_id"], "area": a["area"], "curso_id": c["curso_id"], "curso": c["codigo"], "curso_nome": c["nome"],
                              "uc_codigo": u["codigo"], "uc_nome": u["nome"], "ch": u["ch"], "tipo": tipo, "certificacao": u["certificacao"],
                              "acao": acao, "porque": porque, "demanda": demanda, "outros_habilitados": outros,
                              "ganho_curso_pp": ganho_c, "ganho_area_pp": round(100 * falta * u["ch"] / ch_area, 1),
                              "prioridade": prio, "pontos": pontos, "no_pdi": (c["curso_id"], u["codigo"], tipo) in ja,
                              "prazo_sugerido": (base.hoje + timedelta(days=30 * PRAZO_MESES[prio])).isoformat()})
    itens.sort(key=lambda x: (-x["pontos"], -x["ganho_curso_pp"], x["curso"], x["uc_codigo"]))
    # projeção por área: concluindo as de prioridade alta / todas
    proj = []
    for a in ind["areas"]:
        ch_area = sum(c["ch_total"] for c in a["cursos"]) or 1
        alta = sum(i["ganho_area_pp"] for i in itens if i["area_id"] == a["area_id"] and i["prioridade"] == "alta")
        proj.append({"area_id": a["area_id"], "area": a["area"], "hoje": a["pct"], "com_alta": min(100.0, round(a["pct"] + alta, 1)),
                     "com_todas": 100.0 if ch_area > 1 else a["pct"],
                     "ch_a_desenvolver": round(sum(i["ch"] * (0.5 if i["tipo"] == "completar" else 1) for i in itens
                                                   if i["area_id"] == a["area_id"] and i["tipo"] != "certificacao"), 1)})
    return {"instrutor_id": inst.id, "geral": ind["geral"], "itens": itens, "projecao": proj,
            "resumo": {"total": len(itens), "alta": sum(1 for i in itens if i["prioridade"] == "alta"),
                       "certificacoes": sum(1 for i in itens if i["tipo"] == "certificacao")}}


def equipe(db: Session, unidades: set[int] | None = None, area_id: int | None = None) -> dict:
    """Índice de todos os instrutores ativos (para a lista) e a cobertura de cada área (UCs sem ninguém ou com uma pessoa só)."""
    base = Base(db)
    linhas = []
    for inst in sorted(base.ativos.values(), key=lambda i: i.nome):
        if unidades is not None and inst.unidade_id not in unidades:
            continue
        ind = indice(db, inst.id, base, detalhe=False)
        if area_id and area_id not in {a["area_id"] for a in ind["areas"]}:
            continue
        linhas.append({"instrutor_id": inst.id, "geral": ind["geral"], "multiarea": ind["multiarea"],
                       "areas": [{"area_id": a["area_id"], "area": a["area"], "pct": a["pct"], "principal": a["principal"]} for a in ind["areas"]],
                       "cursos": [{"codigo": c["codigo"], "pct": c["pct"]} for a in ind["areas"] for c in a["cursos"]]})
    cobertura = []
    for aid, area in sorted(base.areas.items(), key=lambda x: x[1].nome):
        if area_id and aid != area_id:
            continue
        if unidades is not None and area.unidade_id not in unidades:
            continue
        ucs = [(cid, u) for cid in base.cursos if base.cursos[cid].area_id == aid for u in base.ucs.get(cid, {}).values()]
        if not ucs:
            continue
        nomes = [base.nomes_habilitados(u, cid) for cid, u in ucs]
        n = [len(x) for x in nomes]
        # as UCs frágeis: ninguém pode dar, ou só uma pessoa (uma falta dela deixa a turma sem aula)
        criticas = sorted([{"curso": base.cursos[cid].codigo, "uc": u["codigo"], "nome": u["nome"], "habilitados": nm}
                           for (cid, u), nm in zip(ucs, nomes) if len(nm) <= 1], key=lambda x: (len(x["habilitados"]), x["curso"], x["uc"]))
        cobertura.append({"area_id": aid, "area": area.nome, "ucs": len(ucs), "sem_ninguem": sum(1 for x in n if x == 0),
                          "um_so": sum(1 for x in n if x == 1), "duas_ou_mais": sum(1 for x in n if x >= 2),
                          "pct_duas_ou_mais": _pct(sum(1 for x in n if x >= 2), len(ucs)), "criticas": criticas})
    cobertura.sort(key=lambda c: (-c["sem_ninguem"], c["pct_duas_ou_mais"], c["area"]))
    media = round(sum(x["geral"] for x in linhas) / len(linhas), 1) if linhas else 0.0
    return {"instrutores": linhas, "media": media, "cobertura": cobertura}
